import math
from datetime import date

import pytest

from app import gbt_predictor

BASE_FEATURES = [
    "log_budget", "runtime_minutes", "release_month", "is_summer", "is_holiday_season",
    "is_english", "mpaa_rating", "is_franchise", "franchise_prior_avg_roi",
    "studio_prior_avg_roi", "director_prior_avg_roi", "actor_prior_avg_roi",
    "imdb_rating", "log_imdb_votes", "rotten_tomatoes_pct", "metacritic_score",
    "tmdb_vote_average", "log_tmdb_vote_count",
    "bluesky_sentiment_score", "log_bluesky_volume", "log_bluesky_avg_engagement",
    "youtube_sentiment_score", "log_youtube_volume", "log_youtube_avg_engagement",
]
GENRE_COLUMNS = ["Action", "Comedy"]
FEATURE_COLUMNS = BASE_FEATURES + [f"genre_{g}" for g in GENRE_COLUMNS]

FAKE_METADATA = {
    "feature_columns": FEATURE_COLUMNS,
    "genre_columns": GENRE_COLUMNS,
    "mpaa_categories": ["G", "PG", "PG-13", "R", "Unrated"],
    "runtime_median": 110.0,
    "prior_avg_lookups": {
        "franchise_prior_avg_roi": {"5": 2.5},
        "studio_prior_avg_roi": {"10": 1.8},
        "director_prior_avg_roi": {},
        "actor_prior_avg_roi": {},
    },
}


class FakeBooster:
    """Records the feature row it was called with and returns a fixed
    (log-space) prediction - lets tests verify feature construction without
    needing a real trained model file on disk.
    """

    def __init__(self, log_value: float):
        self.log_value = log_value
        self.last_row = None

    def predict(self, row):
        self.last_row = row[0]
        return [self.log_value]


@pytest.fixture
def fake_model(monkeypatch):
    # Deliberately "crossed" quantiles (p25's booster returns the largest
    # value) to verify predict_verdict's sort-based crossing guard actually
    # reorders them, rather than trusting each booster's own alpha.
    boosters = {0.25: FakeBooster(math.log(5)), 0.50: FakeBooster(math.log(3)), 0.75: FakeBooster(math.log(1))}
    monkeypatch.setattr(gbt_predictor, "_boosters", boosters)
    monkeypatch.setattr(gbt_predictor, "_metadata", FAKE_METADATA)
    return boosters


def test_bucket_boundaries():
    assert gbt_predictor._bucket(0.999) == "flop"
    assert gbt_predictor._bucket(1.0) == "solid"
    assert gbt_predictor._bucket(3.0) == "hit"
    assert gbt_predictor._bucket(5.0) == "blockbuster"


def test_season_features():
    month, is_summer, is_holiday = gbt_predictor._season_features(date(2026, 7, 15))
    assert (month, is_summer, is_holiday) == (7, 1, 0)

    month, is_summer, is_holiday = gbt_predictor._season_features(date(2026, 12, 1))
    assert (month, is_summer, is_holiday) == (12, 0, 1)


def test_predict_verdict_returns_none_without_budget():
    movie = {"budget_usd": None}
    assert gbt_predictor.predict_verdict(movie, None, None, None) is None

    movie = {"budget_usd": 0}
    assert gbt_predictor.predict_verdict(movie, None, None, None) is None


def test_predict_verdict_sorts_crossed_quantiles(fake_model):
    movie = {
        "budget_usd": 100_000_000,
        "release_date": date(2026, 7, 15),
        "original_language": "en",
        "mpaa_rating": "PG-13",
        "franchise_id": None,
        "studio_id": None,
        "genres": ["Action"],
        "runtime_minutes": 120,
    }
    result = gbt_predictor.predict_verdict(movie, None, None, None)

    assert result["roi_multiple_p25"] == pytest.approx(1.0)
    assert result["roi_multiple_p50"] == pytest.approx(3.0)
    assert result["roi_multiple_p75"] == pytest.approx(5.0)
    assert result["verdict_bucket"] == gbt_predictor._bucket(3.0)
    assert result["method"] == gbt_predictor.METHOD


def test_predict_verdict_feature_vector_missing_data_is_nan(fake_model):
    movie = {
        "budget_usd": 50_000_000,
        "release_date": None,
        "original_language": "fr",
        "mpaa_rating": None,
        "franchise_id": None,
        "studio_id": None,
        "genres": [],
        "runtime_minutes": None,
    }
    gbt_predictor.predict_verdict(movie, primary_director_id=None, lead_actor_id=None, critic_scores=None)

    row = dict(zip(FEATURE_COLUMNS, fake_model[0.50].last_row))
    assert math.isnan(row["release_month"])
    assert math.isnan(row["imdb_rating"])
    assert math.isnan(row["bluesky_sentiment_score"])
    assert row["runtime_minutes"] == FAKE_METADATA["runtime_median"]
    assert row["is_english"] == 0
    assert row["mpaa_rating"] == FAKE_METADATA["mpaa_categories"].index("Unrated")
    assert row["genre_Action"] == 0
    assert row["genre_Comedy"] == 0


def test_predict_verdict_uses_prior_avg_lookups(fake_model):
    movie = {
        "budget_usd": 50_000_000,
        "release_date": date(2026, 1, 1),
        "original_language": "en",
        "mpaa_rating": "R",
        "franchise_id": 5,
        "studio_id": 10,
        "genres": ["Comedy"],
        "runtime_minutes": 90,
    }
    gbt_predictor.predict_verdict(movie, primary_director_id=None, lead_actor_id=None, critic_scores=None)

    row = dict(zip(FEATURE_COLUMNS, fake_model[0.50].last_row))
    assert row["franchise_prior_avg_roi"] == 2.5
    assert row["studio_prior_avg_roi"] == 1.8
    assert row["is_franchise"] == 1
    assert row["genre_Comedy"] == 1
    assert row["genre_Action"] == 0


def test_predict_verdict_uses_critic_and_sentiment_data(fake_model):
    movie = {
        "budget_usd": 50_000_000,
        "release_date": date(2026, 1, 1),
        "original_language": "en",
        "mpaa_rating": "R",
        "franchise_id": None,
        "studio_id": None,
        "genres": [],
        "runtime_minutes": 90,
    }
    critic_scores = {"imdb_rating": 7.5, "imdb_votes": 1000, "rotten_tomatoes_pct": 80}
    sentiment = {"bluesky_sentiment_score": 0.5, "bluesky_volume": 20, "youtube_avg_engagement": 30}

    gbt_predictor.predict_verdict(movie, None, None, critic_scores, sentiment)

    row = dict(zip(FEATURE_COLUMNS, fake_model[0.50].last_row))
    assert row["imdb_rating"] == 7.5
    assert row["log_imdb_votes"] == math.log1p(1000)
    assert row["rotten_tomatoes_pct"] == 80
    assert row["bluesky_sentiment_score"] == 0.5
    assert row["log_bluesky_volume"] == math.log1p(20)
    assert row["log_youtube_avg_engagement"] == math.log1p(30)
    # Not provided - should still fall back to NaN, not KeyError/0.
    assert math.isnan(row["metacritic_score"])
    assert math.isnan(row["youtube_sentiment_score"])
