"""Shared post-processing for every sentiment-source flow (reddit_*,
youtube_comment_sentiment.py, bluesky_*): turns a list of source-agnostic
items into the metrics sentiment_snapshots stores. Kept separate from each
source's own client (pure API I/O) and from the flow modules (DB
orchestration) so every source computes volume/engagement/sentiment the
exact same way - one lexicon, one aggregation, not a copy per source.

Each source client normalizes its own raw response into
{"id", "text", "engagement"} dicts before calling summarize_items() (e.g.
Reddit's title+selftext get joined into one text field, its upvote-based
post "score" becomes "engagement").

v1 metrics, per the planning doc: mention/comment volume and average
engagement are the primary, trustworthy signal. The lexicon sentiment score
is an explicit stretch goal - a small hand-built word list, not a model -
and is None whenever an item's text matches none of the lexicon's words,
rather than defaulting to a fake 0.0.
"""

import re

_POSITIVE_WORDS = {
    "amazing", "incredible", "masterpiece", "excellent", "great", "love",
    "loved", "awesome", "fantastic", "brilliant", "perfect", "best",
    "hyped", "excited", "stunning", "beautiful", "impressive", "solid",
    "underrated", "banger", "phenomenal", "wonderful", "fun", "enjoyed",
    "enjoyable", "recommend", "goat", "peak",
}
_NEGATIVE_WORDS = {
    "terrible", "awful", "worst", "disappointing", "disappointed", "bad",
    "boring", "bomb", "flop", "hate", "hated", "mediocre", "mess",
    "overrated", "waste", "cringe", "bland", "forgettable", "disaster",
    "underwhelming", "letdown", "trash", "garbage", "unwatchable",
}

_WORD_RE = re.compile(r"[a-z']+")


def _lexicon_score(text: str) -> tuple[int, int]:
    words = _WORD_RE.findall(text.lower())
    pos = sum(1 for w in words if w in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w in _NEGATIVE_WORDS)
    return pos, neg


def summarize_items(items: list[dict]) -> dict:
    """items: list of {"id", "text", "engagement"} dicts, source-agnostic.

    Returns {volume, avg_engagement_score, sentiment_score, sample_ids}.
    avg_engagement_score and sentiment_score are None (not 0) when there are
    no items / no lexicon hits, so "no signal" is never confused with
    "neutral/zero signal" downstream.
    """
    if not items:
        return {"volume": 0, "avg_engagement_score": None, "sentiment_score": None, "sample_ids": []}

    total_pos = 0
    total_neg = 0
    for item in items:
        pos, neg = _lexicon_score(item.get("text", ""))
        total_pos += pos
        total_neg += neg

    sentiment_score = None
    if total_pos + total_neg > 0:
        sentiment_score = round((total_pos - total_neg) / (total_pos + total_neg), 4)

    avg_engagement = sum(item.get("engagement", 0) for item in items) / len(items)

    return {
        "volume": len(items),
        "avg_engagement_score": round(avg_engagement, 2),
        "sentiment_score": sentiment_score,
        "sample_ids": [item["id"] for item in items if item.get("id")],
    }
