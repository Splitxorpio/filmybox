"""Consensus-gated dollar-figure extraction from Bluesky post text.

Social posts are not an authoritative source - direct testing this session
found real disagreement between posts on the same movie (Dune Part Two:
$165M, $190M, and $250M in different posts) and false positives (a "budget"
search hit about an unrelated government prison budget). This deliberately
trades recall for precision: only accept a value multiple independent posts
corroborate, never "take the first number found."
"""

import re

_MONEY_RE = re.compile(
    r"\$\s?(\d+(?:\.\d+)?)\s?(million|m|billion|b)\b",
    re.IGNORECASE,
)

_BUCKET_SIZE = 5_000_000  # round to nearest $5M when grouping candidate values

MIN_CORROBORATING_POSTS = 2
MIN_MARGIN_OVER_RUNNER_UP = 2.0


def _extract_candidates(text: str, title: str) -> list[int]:
    """Only counts a $ figure that appears in the same paragraph (blank-
    line-separated block) as an occurrence of `title`. Two real post
    formats confirmed this session, calibrated against real examples:
    - a "fact sheet" single-movie post puts the title and its budget on
      adjacent lines separated by a single newline, no blank line between
      ("OPPENHEIMER (2023)\nBudget: $100M");
    - a multi-movie comparison/list post separates each entry with a
      blank line ("OPPENHEIMER - $100M\n\nSUPER MARIO BROS. - $100M\n\n...").
    A single-newline split is too strict (breaks the first case); a plain
    character-distance window is too loose (bleeds across list entries in
    the second case, confirmed - adjacent entries sat within any
    reasonable radius of each other). Splitting on blank lines gets both
    right.
    """
    title_lower = title.lower()
    values = []
    for paragraph in re.split(r"\n\s*\n", text):
        if title_lower not in paragraph.lower():
            continue
        for match in _MONEY_RE.finditer(paragraph):
            amount = float(match.group(1))
            multiplier = 1_000_000_000 if match.group(2).lower().startswith("b") else 1_000_000
            values.append(int(amount * multiplier))
    return values


def extract_budget_consensus(posts: list[str], title: str) -> int | None:
    """Returns a consensus USD budget from a list of post texts, or None if
    no value clears the corroboration bar (at least MIN_CORROBORATING_POSTS
    posts agreeing on the same ~$5M bucket, and that bucket must have at
    least MIN_MARGIN_OVER_RUNNER_UP times as many posts as the next-largest
    bucket - avoids picking an arbitrary winner out of a genuinely
    disputed/ambiguous spread).
    """
    bucket_counts: dict[int, list[int]] = {}
    for post in posts:
        for value in _extract_candidates(post, title):
            bucket = round(value / _BUCKET_SIZE) * _BUCKET_SIZE
            bucket_counts.setdefault(bucket, []).append(value)

    if not bucket_counts:
        return None

    ranked = sorted(bucket_counts.items(), key=lambda kv: len(kv[1]), reverse=True)
    top_bucket, top_values = ranked[0]
    top_count = len(top_values)

    if top_count < MIN_CORROBORATING_POSTS:
        return None

    runner_up_count = len(ranked[1][1]) if len(ranked) > 1 else 0
    if runner_up_count > 0 and top_count < runner_up_count * MIN_MARGIN_OVER_RUNNER_UP:
        return None

    return int(sum(top_values) / len(top_values))
