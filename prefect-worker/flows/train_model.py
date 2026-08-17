"""Trains a GBT (LightGBM quantile regression) model on ROI multiple, as a
real predictor to compare against comp_heuristic_v1, gbt_v1, and gbt_v2, all
already in `verdicts`.

Uses the same target (total_worldwide / budget_usd) and the same
flop/solid/hit/blockbuster bucket thresholds as the heuristic (imported
from stage_scan.py, not duplicated - train_model.py lives in the same
service/package). v1 was pre-release-only features, for a fair comparison
against the heuristic's own limitation. v2 added critic-score features
(imdb/RT/Metacritic/tmdb vote aggregates). v3 (current) adds sentiment
features from Bluesky (post_release stage) and YouTube trailer comments -
both additive/NaN-native, same pattern as v2's critic scores.

Before wiring these in, checked coverage against the time-based train/test
split and found two coverage-skew bugs (same shape as the one that broke the
first v2 attempt): YouTube comment coverage was 100% post-cutoff (zero
training examples) because trailer_backfill.py's movie selection is
recency-first by design; Bluesky's post_release coverage was the mirror
image, 100% pre-cutoff (zero test examples), because its backfill is
oldest-first by design. Fixed with two narrowly-scoped topup flows
(trailer_backfill_training_topup.py, bluesky_sentiment_topup.py) targeting
exactly the missing side of each - see planning doc's GBT v3 section.

Also does real hyperparameter tuning now (a small grid search over
num_leaves/learning_rate/min_data_in_leaf, PARAM_GRID below) - LightGBM's
defaults had been carried forward unchanged since v1 and never actually
tuned. Uses a proper 3-way time-ordered split (train/val/test): tuning only
ever sees train+val, the test set stays untouched until the one final
evaluation, preserving the same held-out discipline every accuracy
comparison this session has relied on.

Batch-precomputes predictions for every movie with a budget (released or
not) and writes them into `verdicts` with method=MODEL_METHOD - like the
heuristic, serving is precompute-and-store, not live in-process (see
planning doc's Model Serving section for why live serving is deferred).

Run manually (module form, see tmdb_backfill.py's docstring for why, and
for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.train_model
"""

import json
import math
import os

import lightgbm as lgb
import numpy as np
import pandas as pd

from db import get_connection, get_latest_stages, get_movies_for_training, upsert_verdict
from flows.stage_scan import BUCKET_THRESHOLDS, _bucket

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_METHOD = "gbt_v3"
QUANTILES = [0.25, 0.50, 0.75]
TEST_FRACTION = 0.20
VAL_FRACTION = 0.15  # carved out of the pre-test portion, for hyperparameter
# tuning only - the test set is never touched until the one final evaluation,
# same discipline the whole session's accuracy comparisons have relied on.
TOP_N_GENRES = 15

# Small grid, not exhaustive - LightGBM defaults (num_leaves=31,
# learning_rate=0.05, min_data_in_leaf=10) were carried forward unchanged
# from v1 through v3 and never actually tuned. Kept intentionally small
# given ~2,400 training rows: a wide search on this little data would just
# overfit the validation set's own noise.
PARAM_GRID = [
    {"num_leaves": nl, "learning_rate": lr, "min_data_in_leaf": mdl}
    for nl in (15, 31, 63)
    for lr in (0.03, 0.05, 0.1)
    for mdl in (5, 10, 20)
]
EARLY_STOPPING_ROUNDS = 20
MAX_BOOST_ROUNDS = 500


def _season_features(release_date) -> tuple[int, int, int]:
    month = release_date.month
    return month, int(month in (5, 6, 7, 8)), int(month in (11, 12))


def _build_features(raw: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw)
    df = df[df["release_date"].notna()].copy()
    df.sort_values("release_date", inplace=True)
    df.reset_index(drop=True, inplace=True)

    df["total_worldwide"] = df["total_worldwide"].astype(float)
    df["budget_usd"] = df["budget_usd"].astype(float)

    df["roi"] = np.where(
        df["total_worldwide"].notna() & (df["budget_usd"] > 0),
        df["total_worldwide"] / df["budget_usd"],
        np.nan,
    )
    df["log_roi"] = np.log(df["roi"])

    df["log_budget"] = np.log1p(df["budget_usd"])

    season = df["release_date"].apply(_season_features)
    df["release_month"] = season.apply(lambda t: t[0])
    df["is_summer"] = season.apply(lambda t: t[1])
    df["is_holiday_season"] = season.apply(lambda t: t[2])

    df["is_english"] = (df["original_language"] == "en").astype(int)
    df["mpaa_rating"] = df["mpaa_rating"].fillna("Unrated").astype("category")

    genre_counts: dict[str, int] = {}
    for genres in df["genres"]:
        for g in genres or []:
            genre_counts[g] = genre_counts.get(g, 0) + 1
    top_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)[:TOP_N_GENRES]
    for g in top_genres:
        df[f"genre_{g}"] = df["genres"].apply(lambda gs, g=g: int(g in (gs or [])))

    for col in ("imdb_rating", "rotten_tomatoes_pct", "metacritic_score", "tmdb_vote_average"):
        df[col] = df[col].astype(float)
    df["log_imdb_votes"] = np.log1p(df["imdb_votes"].astype(float))
    df["log_tmdb_vote_count"] = np.log1p(df["tmdb_vote_count"].astype(float))

    df["bluesky_sentiment_score"] = df["bluesky_sentiment_score"].astype(float)
    df["log_bluesky_volume"] = np.log1p(df["bluesky_volume"].astype(float))
    df["log_bluesky_avg_engagement"] = np.log1p(df["bluesky_avg_engagement"].astype(float))
    df["youtube_sentiment_score"] = df["youtube_sentiment_score"].astype(float)
    df["log_youtube_volume"] = np.log1p(df["youtube_volume"].astype(float))
    df["log_youtube_avg_engagement"] = np.log1p(df["youtube_avg_engagement"].astype(float))

    df["is_franchise"] = df["franchise_id"].notna().astype(int)
    df["primary_director_id"] = df["director_ids"].apply(lambda ids: ids[0] if ids else None)

    for group_col, new_col in [
        ("franchise_id", "franchise_prior_avg_roi"),
        ("studio_id", "studio_prior_avg_roi"),
        ("primary_director_id", "director_prior_avg_roi"),
        ("lead_actor_id", "actor_prior_avg_roi"),
    ]:
        df[new_col] = df.groupby(group_col)["roi"].transform(lambda s: s.expanding(min_periods=1).mean().shift(1))

    df["runtime_minutes"] = df["runtime_minutes"].fillna(df["runtime_minutes"].median())

    return df, top_genres


def _feature_columns(top_genres: list[str]) -> list[str]:
    return [
        "log_budget",
        "runtime_minutes",
        "release_month",
        "is_summer",
        "is_holiday_season",
        "is_english",
        "mpaa_rating",
        "is_franchise",
        "franchise_prior_avg_roi",
        "studio_prior_avg_roi",
        "director_prior_avg_roi",
        "actor_prior_avg_roi",
        "imdb_rating",
        "log_imdb_votes",
        "rotten_tomatoes_pct",
        "metacritic_score",
        "tmdb_vote_average",
        "log_tmdb_vote_count",
        "bluesky_sentiment_score",
        "log_bluesky_volume",
        "log_bluesky_avg_engagement",
        "youtube_sentiment_score",
        "log_youtube_volume",
        "log_youtube_avg_engagement",
    ] + [f"genre_{g}" for g in top_genres]


def _train_quantile_models(
    X_train, y_train, feature_cols, hp: dict, num_boost_round: int
) -> dict[float, lgb.Booster]:
    train_set = lgb.Dataset(
        X_train[feature_cols], label=y_train, categorical_feature=["mpaa_rating"], free_raw_data=False
    )
    boosters = {}
    for q in QUANTILES:
        params = {
            "objective": "quantile",
            "alpha": q,
            "metric": "quantile",
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbose": -1,
            **hp,
        }
        boosters[q] = lgb.train(params, train_set, num_boost_round=num_boost_round)
    return boosters


def _tune_hyperparameters(train_df, val_df, feature_cols) -> tuple[dict, int]:
    """Small grid search over PARAM_GRID, using the p50 (median) objective
    only - tuning all 3 quantile models independently would triple the
    search cost for the same essential decision (tree complexity/learning
    rate), and the chosen hyperparameters are applied to all 3 afterward.
    Selects by validation-set exact-bucket accuracy (the metric actually
    reported and compared against the other methods), not quantile loss
    directly - loss and bucket accuracy don't always agree, and bucket
    accuracy is what matters here. Early stopping on quantile loss picks
    num_boost_round per candidate; the winning candidate's best_iteration is
    reused for the final fit.
    """
    train_set = lgb.Dataset(
        train_df[feature_cols], label=train_df["log_roi"], categorical_feature=["mpaa_rating"], free_raw_data=False
    )
    val_set = lgb.Dataset(
        val_df[feature_cols], label=val_df["log_roi"], categorical_feature=["mpaa_rating"], reference=train_set
    )
    val_actual_bucket = val_df["roi"].apply(_bucket)

    best = None
    for hp in PARAM_GRID:
        params = {
            "objective": "quantile",
            "alpha": 0.5,
            "metric": "quantile",
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbose": -1,
            **hp,
        }
        booster = lgb.train(
            params,
            train_set,
            num_boost_round=MAX_BOOST_ROUNDS,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False), lgb.log_evaluation(0)],
        )
        val_pred_p50 = np.exp(booster.predict(val_df[feature_cols], num_iteration=booster.best_iteration))
        val_pred_bucket = pd.Series(val_pred_p50, index=val_df.index).apply(_bucket)
        exact, within_one = _bucket_accuracy(val_pred_bucket, val_actual_bucket)

        if best is None or exact > best["exact"] or (exact == best["exact"] and within_one > best["within_one"]):
            best = {"hp": hp, "exact": exact, "within_one": within_one, "num_boost_round": booster.best_iteration}

    print(
        f"[train-model] tuning: best hp={best['hp']} num_boost_round={best['num_boost_round']} "
        f"(val exact={best['exact']:.1%} within_one={best['within_one']:.1%}, "
        f"searched {len(PARAM_GRID)} combos)"
    )
    return best["hp"], best["num_boost_round"]


def _predict(boosters: dict[float, lgb.Booster], X, feature_cols) -> np.ndarray:
    """Returns (n, 3) array of [p25, p50, p75] ROI multiples, sorted per-row
    to guard against quantile crossing (each booster is trained independently).
    """
    preds = np.column_stack([np.exp(boosters[q].predict(X[feature_cols])) for q in QUANTILES])
    preds.sort(axis=1)
    return preds


def _entity_avg_lookup(df: pd.DataFrame, group_col: str) -> dict[str, float]:
    """Plain (non-expanding, all-history) average ROI per entity - a static
    snapshot for live serving (api/gbt_predictor.py) to look up prior track
    record for movies outside the training set, distinct from the
    leakage-safe expanding-mean feature used during training itself.
    """
    means = df.groupby(group_col)["roi"].mean().dropna()
    return {str(int(k)): float(v) for k, v in means.items()}


def _bucket_accuracy(pred_bucket: pd.Series, actual_bucket: pd.Series) -> tuple[float, float]:
    order = [label for _, label in BUCKET_THRESHOLDS] + ["blockbuster"]
    exact = (pred_bucket == actual_bucket).mean()
    within_one = (
        (pred_bucket.map(order.index) - actual_bucket.map(order.index)).abs() <= 1
    ).mean()
    return exact, within_one


def train_model_flow():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            raw = get_movies_for_training(cur)
        print(f"[train-model] {len(raw)} movies with a budget pulled from DB")

        df, top_genres = _build_features(raw)
        feature_cols = _feature_columns(top_genres)

        labeled = df[df["roi"].notna()].copy()
        test_cutoff_idx = int(len(labeled) * (1 - TEST_FRACTION))
        train_val_df = labeled.iloc[:test_cutoff_idx]
        test_df = labeled.iloc[test_cutoff_idx:]

        val_cutoff_idx = int(len(train_val_df) * (1 - VAL_FRACTION / (1 - TEST_FRACTION)))
        tune_train_df = train_val_df.iloc[:val_cutoff_idx]
        val_df = train_val_df.iloc[val_cutoff_idx:]
        print(
            f"[train-model] {len(tune_train_df)} train / {len(val_df)} val / {len(test_df)} test "
            f"(time-split at {test_df.iloc[0]['release_date']})"
        )

        best_hp, best_num_boost_round = _tune_hyperparameters(tune_train_df, val_df, feature_cols)

        # Final fit uses train+val combined (all pre-test data) at the
        # tuned hyperparameters - the validation split's only job was
        # picking these, it doesn't need to stay held out for the final model.
        boosters = _train_quantile_models(
            train_val_df, train_val_df["log_roi"], feature_cols, best_hp, best_num_boost_round
        )

        test_preds = _predict(boosters, test_df, feature_cols)
        test_df = test_df.copy()
        test_df["pred_p50"] = test_preds[:, 1]
        test_df["pred_bucket"] = test_df["pred_p50"].apply(_bucket)
        test_df["actual_bucket"] = test_df["roi"].apply(_bucket)

        mae_log_roi = (np.log(test_df["pred_p50"]) - test_df["log_roi"]).abs().mean()
        exact, within_one = _bucket_accuracy(test_df["pred_bucket"], test_df["actual_bucket"])
        print(f"[train-model] {MODEL_METHOD} test MAE (log-ROI): {mae_log_roi:.3f}")
        print(f"[train-model] {MODEL_METHOD} bucket accuracy: exact={exact:.1%} within_one={within_one:.1%}")

        for other_method in ("comp_heuristic_v1", "gbt_v1", "gbt_v2"):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT v.movie_id, v.verdict_bucket, v.actual_bucket
                    FROM verdicts v
                    WHERE v.method = %s AND v.movie_id = ANY(%s)
                        AND v.verdict_bucket IS NOT NULL AND v.actual_bucket IS NOT NULL
                    """,
                    (other_method, test_df["id"].tolist()),
                )
                other_rows = cur.fetchall()
            if other_rows:
                o_df = pd.DataFrame(other_rows, columns=["movie_id", "verdict_bucket", "actual_bucket"])
                o_exact, o_within_one = _bucket_accuracy(o_df["verdict_bucket"], o_df["actual_bucket"])
                print(
                    f"[train-model] {other_method} on same {len(o_df)} test movies: "
                    f"exact={o_exact:.1%} within_one={o_within_one:.1%}"
                )

        importances = boosters[0.50].feature_importance(importance_type="gain")
        top_features = sorted(zip(feature_cols, importances), key=lambda t: -t[1])[:10]
        print("[train-model] top features (gain):")
        for name, gain in top_features:
            print(f"  {name}: {gain:.0f}")

        os.makedirs(MODEL_DIR, exist_ok=True)
        for q, booster in boosters.items():
            booster.save_model(os.path.join(MODEL_DIR, f"gbt_roi_p{int(q * 100)}_{MODEL_METHOD}.txt"))
        prior_avg_lookups = {
            "franchise_prior_avg_roi": _entity_avg_lookup(df, "franchise_id"),
            "studio_prior_avg_roi": _entity_avg_lookup(df, "studio_id"),
            "director_prior_avg_roi": _entity_avg_lookup(df, "primary_director_id"),
            "actor_prior_avg_roi": _entity_avg_lookup(df, "lead_actor_id"),
        }
        with open(os.path.join(MODEL_DIR, f"feature_metadata_{MODEL_METHOD}.json"), "w") as f:
            json.dump(
                {
                    "feature_columns": feature_cols,
                    "genre_columns": top_genres,
                    "mpaa_categories": df["mpaa_rating"].cat.categories.tolist(),
                    "runtime_median": float(df["runtime_minutes"].median()),
                    "prior_avg_lookups": prior_avg_lookups,
                },
                f,
                indent=2,
            )
        print(f"[train-model] saved boosters + feature metadata to {MODEL_DIR}")

        with conn.cursor() as cur:
            latest_stages = get_latest_stages(cur)

        all_preds = _predict(boosters, df, feature_cols)
        written = 0
        with conn.cursor() as cur:
            for i, row in df.iterrows():
                movie_id = int(row["id"])
                has_actual = not math.isnan(row["roi"])
                stage = latest_stages.get(movie_id, "post_release" if has_actual else "announcement")
                p25, p50, p75 = all_preds[i]
                verdict = {
                    "comp_count": len(train_val_df),
                    "roi_multiple_p25": float(p25),
                    "roi_multiple_p50": float(p50),
                    "roi_multiple_p75": float(p75),
                    "verdict_bucket": _bucket(p50),
                    "comp_movie_ids": [],
                    "actual_roi_multiple": float(row["roi"]) if has_actual else None,
                    "actual_bucket": _bucket(row["roi"]) if has_actual else None,
                }
                upsert_verdict(cur, movie_id, stage, verdict, method=MODEL_METHOD)
                written += 1
        conn.commit()
        print(f"[train-model] wrote {written} {MODEL_METHOD} verdict rows")
    finally:
        conn.close()

    print("[train-model] done")


if __name__ == "__main__":
    train_model_flow()
