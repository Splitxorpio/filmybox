from wikipedia_client import _parse_money


def test_parse_money_million():
    assert _parse_money("$185 million") == 185_000_000


def test_parse_money_billion():
    assert _parse_money("$1.5 billion") == 1_500_000_000


def test_parse_money_short_units():
    assert _parse_money("$100m") == 100_000_000
    assert _parse_money("$2bn") == 2_000_000_000


def test_parse_money_range_uses_midpoint():
    assert _parse_money("$190-250 million") == 220_000_000


def test_parse_money_range_with_en_dash():
    assert _parse_money("$190–250 million") == 220_000_000


def test_parse_money_range_with_dollar_on_second_bound():
    assert _parse_money("$190-$250 million") == 220_000_000


def test_parse_money_bare_large_number():
    assert _parse_money("$117,092") == 117_092


def test_parse_money_bare_small_number_rejected():
    # No unit qualifier and too small to plausibly be a real budget.
    assert _parse_money("$5") is None


def test_parse_money_no_dollar_sign_returns_none():
    assert _parse_money("€8 million") is None


def test_parse_money_no_match_returns_none():
    assert _parse_money("Budget unknown") is None
