from budget_extraction import _extract_candidates, extract_budget_consensus


def test_extract_candidates_fact_sheet_format():
    # Title and budget on adjacent lines, single newline, no blank line.
    text = "OPPENHEIMER (2023)\nBudget: $100M"
    assert _extract_candidates(text, "Oppenheimer") == [100_000_000]


def test_extract_candidates_comparison_list_format():
    text = "OPPENHEIMER - $100M\n\nSUPER MARIO BROS. - $100M\n\nBARBIE - $145M"
    assert _extract_candidates(text, "Oppenheimer") == [100_000_000]
    assert _extract_candidates(text, "Barbie") == [145_000_000]


def test_extract_candidates_ignores_other_movies_paragraph():
    text = "SOME OTHER MOVIE - $9999M\n\nOPPENHEIMER - $100M"
    assert _extract_candidates(text, "Oppenheimer") == [100_000_000]


def test_extract_candidates_billion_unit():
    text = "AVATAR budget: $2.5 billion"
    assert _extract_candidates(text, "Avatar") == [2_500_000_000]


def test_extract_candidates_no_title_match_returns_empty():
    text = "Some unrelated post about a government budget of $500M"
    assert _extract_candidates(text, "Oppenheimer") == []


def test_consensus_needs_minimum_corroboration():
    # Only one post mentions a value - below MIN_CORROBORATING_POSTS.
    posts = ["OPPENHEIMER budget: $100M"]
    assert extract_budget_consensus(posts, "Oppenheimer") is None


def test_consensus_reached_with_corroborating_posts():
    posts = ["OPPENHEIMER budget: $100M", "OPPENHEIMER cost $100M to make"]
    assert extract_budget_consensus(posts, "Oppenheimer") == 100_000_000


def test_consensus_rejected_without_sufficient_margin():
    # 2 posts say $100M, 2 posts say $190M - top bucket doesn't clear
    # MIN_MARGIN_OVER_RUNNER_UP (2x) over the runner-up.
    posts = [
        "OPPENHEIMER budget: $100M",
        "OPPENHEIMER cost $100M",
        "OPPENHEIMER budget: $190M",
        "OPPENHEIMER cost $190M",
    ]
    assert extract_budget_consensus(posts, "Oppenheimer") is None


def test_consensus_accepted_with_sufficient_margin():
    # 3 posts agree on ~$100M, 1 disagreeing post - 3 >= 1*2.0 margin met.
    posts = [
        "OPPENHEIMER budget: $100M",
        "OPPENHEIMER cost $100M",
        "OPPENHEIMER was $100M",
        "OPPENHEIMER budget: $250M",
    ]
    assert extract_budget_consensus(posts, "Oppenheimer") == 100_000_000


def test_consensus_no_posts_returns_none():
    assert extract_budget_consensus([], "Oppenheimer") is None
