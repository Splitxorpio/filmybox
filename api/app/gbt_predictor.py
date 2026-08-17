"""Live in-process serving for the gbt_v3 model - Path 1 from the planning
doc's Model Serving section (FastAPI loads the boosters into memory, calls
predict() directly in the request handler, no separate service).

Mirrors prefect-worker/flows/train_model.py's feature building, single-row
instead of batch, duplicated per this project's established cross-service
pattern (api/ and prefect-worker/ share no code). No pandas/scikit-learn
needed here - LightGBM's native Booster.predict() accepts plain lists, and
the prior-avg-ROI features that train_model.py computes via a pandas
expanding-mean are exported as static lookup dicts in feature_metadata_gbt_v3.json
for this module to read directly.

Was stuck on METHOD="gbt_v2" for a while after gbt_v3 shipped (missing the
sentiment features and tuned hyperparameters entirely) - found and fixed
while wiring up Redis caching for this endpoint, since caching a known-stale
model's predictions would have been counterproductive.

Lazy-loaded module-level singleton, same shape as
prefect-worker/embedding_client.py's _get_model().
"""

import json
import math
import os

import lightgbm as lgb

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
METHOD = "gbt_v3"
QUANTILES = [0.25, 0.50, 0.75]

BUCKET_THRESHOLDS = [(1, "flop"), (3, "solid"), (5, "hit")]  # else blockbuster

_boosters: dict[float, lgb.Booster] | None = None
_metadata: dict | None = None


def _bucket(roi_multiple: float) -> str:
    for threshold, label in BUCKET_THRESHOLDS:
        if roi_multiple < threshold:
            return label
    return "blockbuster"


def _load() -> None:
    global _boosters, _metadata
    if _boosters is not None:
        return
    boosters = {}
    for q in QUANTILES:
        path = os.path.join(MODEL_DIR, f"gbt_roi_p{int(q * 100)}_{METHOD}.txt")
        boosters[q] = lgb.Booster(model_file=path)
    with open(os.path.join(MODEL_DIR, f"feature_metadata_{METHOD}.json")) as f:
        metadata = json.load(f)
    _boosters, _metadata = boosters, metadata


def _season_features(release_date) -> tuple[int, int, int]:
    month = release_date.month
    return month, int(month in (5, 6, 7, 8)), int(month in (11, 12))


def predict_verdict(
    movie: dict,
    primary_director_id: int | None,
    lead_actor_id: int | None,
    critic_scores: dict | None,
    sentiment: dict | None = None,
) -> dict | None:
    """Returns {"roi_multiple_p25/p50/p75", "verdict_bucket", "method"}, or
    None if the movie has no budget (ROI is undefined without one).
    """
    if not movie.get("budget_usd"):
        return None

    _load()

    if movie.get("release_date"):
        month, is_summer, is_holiday_season = _season_features(movie["release_date"])
    else:
        month, is_summer, is_holiday_season = math.nan, math.nan, math.nan

    lookups = _metadata["prior_avg_lookups"]
    mpaa_categories = _metadata["mpaa_categories"]
    mpaa_rating = movie.get("mpaa_rating") or "Unrated"
    mpaa_code = mpaa_categories.index(mpaa_rating) if mpaa_rating in mpaa_categories else math.nan

    cs = critic_scores or {}
    sent = sentiment or {}
    genres = movie.get("genres") or []

    features = {
        "log_budget": math.log1p(float(movie["budget_usd"])),
        "runtime_minutes": movie.get("runtime_minutes") or _metadata["runtime_median"],
        "release_month": month,
        "is_summer": is_summer,
        "is_holiday_season": is_holiday_season,
        "is_english": int(movie.get("original_language") == "en"),
        "mpaa_rating": mpaa_code,
        "is_franchise": int(movie.get("franchise_id") is not None),
        "franchise_prior_avg_roi": lookups["franchise_prior_avg_roi"].get(str(movie.get("franchise_id")), math.nan),
        "studio_prior_avg_roi": lookups["studio_prior_avg_roi"].get(str(movie.get("studio_id")), math.nan),
        "director_prior_avg_roi": lookups["director_prior_avg_roi"].get(str(primary_director_id), math.nan),
        "actor_prior_avg_roi": lookups["actor_prior_avg_roi"].get(str(lead_actor_id), math.nan),
        "imdb_rating": cs["imdb_rating"] if cs.get("imdb_rating") is not None else math.nan,
        "log_imdb_votes": math.log1p(cs["imdb_votes"]) if cs.get("imdb_votes") is not None else math.nan,
        "rotten_tomatoes_pct": cs["rotten_tomatoes_pct"] if cs.get("rotten_tomatoes_pct") is not None else math.nan,
        "metacritic_score": cs["metacritic_score"] if cs.get("metacritic_score") is not None else math.nan,
        "tmdb_vote_average": cs["tmdb_vote_average"] if cs.get("tmdb_vote_average") is not None else math.nan,
        "log_tmdb_vote_count": math.log1p(cs["tmdb_vote_count"]) if cs.get("tmdb_vote_count") is not None else math.nan,
        "bluesky_sentiment_score": sent["bluesky_sentiment_score"]
        if sent.get("bluesky_sentiment_score") is not None
        else math.nan,
        "log_bluesky_volume": math.log1p(sent["bluesky_volume"]) if sent.get("bluesky_volume") is not None else math.nan,
        "log_bluesky_avg_engagement": math.log1p(sent["bluesky_avg_engagement"])
        if sent.get("bluesky_avg_engagement") is not None
        else math.nan,
        "youtube_sentiment_score": sent["youtube_sentiment_score"]
        if sent.get("youtube_sentiment_score") is not None
        else math.nan,
        "log_youtube_volume": math.log1p(sent["youtube_volume"]) if sent.get("youtube_volume") is not None else math.nan,
        "log_youtube_avg_engagement": math.log1p(sent["youtube_avg_engagement"])
        if sent.get("youtube_avg_engagement") is not None
        else math.nan,
    }
    for g in _metadata["genre_columns"]:
        features[f"genre_{g}"] = int(g in genres)

    row = [[features[col] for col in _metadata["feature_columns"]]]
    preds = sorted(math.exp(_boosters[q].predict(row)[0]) for q in QUANTILES)
    p25, p50, p75 = preds

    return {
        "roi_multiple_p25": p25,
        "roi_multiple_p50": p50,
        "roi_multiple_p75": p75,
        "verdict_bucket": _bucket(p50),
        "method": METHOD,
    }
