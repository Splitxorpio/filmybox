"""Shared post-processing for both reddit_* flows: turns a list of posts from
reddit_client.search_movie_mentions() into the metrics sentiment_snapshots
stores. Kept separate from reddit_client.py (pure API I/O) and from the flow
modules (DB orchestration) so both flows call the exact same aggregation.

v1 metrics, per the planning doc: mention volume and average engagement
score (Reddit's upvote-based post score) are the primary, trustworthy
signal. The lexicon sentiment score is an explicit stretch goal - a small
hand-built word list, not a model - and is None whenever a post's text
matches none of the lexicon's words, rather than defaulting to a fake 0.0.
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


def summarize_posts(posts: list[dict]) -> dict:
    """Returns {volume, avg_engagement_score, sentiment_score, sample_ids}.
    avg_engagement_score and sentiment_score are None (not 0) when there are
    no posts / no lexicon hits, so "no signal" is never confused with
    "neutral/zero signal" downstream.
    """
    if not posts:
        return {"volume": 0, "avg_engagement_score": None, "sentiment_score": None, "sample_ids": []}

    total_pos = 0
    total_neg = 0
    for p in posts:
        pos, neg = _lexicon_score(f"{p.get('title', '')} {p.get('selftext', '')}")
        total_pos += pos
        total_neg += neg

    sentiment_score = None
    if total_pos + total_neg > 0:
        sentiment_score = round((total_pos - total_neg) / (total_pos + total_neg), 4)

    avg_engagement = sum(p.get("score", 0) for p in posts) / len(posts)

    return {
        "volume": len(posts),
        "avg_engagement_score": round(avg_engagement, 2),
        "sentiment_score": sentiment_score,
        "sample_ids": [p["id"] for p in posts if p.get("id")],
    }
