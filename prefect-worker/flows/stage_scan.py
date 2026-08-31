"""The staged verdict system: detects each movie's current lifecycle stage
(announcement -> teaser -> trailer -> pre_release -> post_release) and
computes a comp-based heuristic verdict (median ROI multiple among the
movie's top embedding comps, bucketed flop/solid/hit/blockbuster).

v1 is deliberately a comp heuristic, not a trained GBT model - see the
planning doc's "Staged Verdict System" section for the reasoning and the
explicit limitation that comps methodology doesn't change across stages
(so the confidence interval doesn't yet narrow the way the product thesis
eventually calls for - that needs real modeling, this is the baseline).

Doubles as both the one-time historical backfill and the ongoing daily scan
via a single query (db.get_movies_needing_stage_check): almost all of the
4,395 historical movies land straight in post_release on first run and are
never revisited; only genuinely active (not-yet-released) movies get
re-scanned on subsequent runs.

Run manually, daily (module form - see tmdb_backfill.py's docstring for why,
and for why this is plain Python, not @flow/@task):
    docker compose run --rm --no-deps prefect-worker python -m flows.stage_scan
"""

import os
from datetime import date, timedelta

from prefect import flow

from db import (
    get_comps_for_verdict,
    get_connection,
    get_movies_needing_stage_check,
    get_trailers_for_movie,
    insert_trailer,
    upsert_trailer_metrics,
    upsert_verdict,
)
from youtube_client import YouTubeQuotaExceeded, get_video_stats, search_trailer

PRE_RELEASE_WINDOW_DAYS = 30
MIN_COMPS_FOR_VERDICT = 3

BUCKET_THRESHOLDS = [(1, "flop"), (3, "solid"), (5, "hit")]  # else blockbuster


def _bucket(roi_multiple: float) -> str:
    for threshold, label in BUCKET_THRESHOLDS:
        if roi_multiple < threshold:
            return label
    return "blockbuster"


def _percentile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = pct * (len(sorted_values) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


def detect_stage(release_date, trailers: list[dict], today: date) -> str:
    if release_date is not None and release_date <= today:
        return "post_release"

    has_trailer = any(
        t["trailer_type"] in ("trailer", "clip") and t["publish_date"] and t["publish_date"] <= today
        for t in trailers
    )
    if has_trailer:
        return "trailer"

    has_teaser = any(
        t["trailer_type"] == "teaser" and t["publish_date"] and t["publish_date"] <= today for t in trailers
    )
    if has_teaser:
        return "teaser"

    if release_date is not None and release_date - today <= timedelta(days=PRE_RELEASE_WINDOW_DAYS):
        return "pre_release"

    return "announcement"


def compute_verdict(cur, movie_id: int, own_budget, own_worldwide) -> dict:
    """ROI = total_worldwide / budget_usd. Comp verdict from the top-15
    embedding comps that have both fields; actual outcome (only meaningful
    once the movie's own box office exists) computed the same way, so the
    two are directly comparable for accuracy checking.
    """
    comps = get_comps_for_verdict(cur, movie_id, limit=15)
    rois = sorted(
        float(worldwide) / float(budget)
        for _, budget, worldwide in comps
        if budget and worldwide and float(budget) > 0
    )

    verdict = {
        "comp_count": len(rois),
        "roi_multiple_p25": None,
        "roi_multiple_p50": None,
        "roi_multiple_p75": None,
        "verdict_bucket": None,
        "comp_movie_ids": [c[0] for c in comps],
        "actual_roi_multiple": None,
        "actual_bucket": None,
    }

    if len(rois) >= MIN_COMPS_FOR_VERDICT:
        p50 = _percentile(rois, 0.50)
        verdict["roi_multiple_p25"] = _percentile(rois, 0.25)
        verdict["roi_multiple_p50"] = p50
        verdict["roi_multiple_p75"] = _percentile(rois, 0.75)
        verdict["verdict_bucket"] = _bucket(p50)

    if own_budget and own_worldwide and float(own_budget) > 0:
        actual_roi = float(own_worldwide) / float(own_budget)
        verdict["actual_roi_multiple"] = actual_roi
        verdict["actual_bucket"] = _bucket(actual_roi)

    return verdict


@flow(name="filmybox-stage-scan", log_prints=True)
def stage_scan_flow():
    youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
    today = date.today()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_needing_stage_check(cur)
        print(f"[stage-scan] {len(movies)} movies need a stage check")

        stage_counts: dict[str, int] = {}
        youtube_limited = False

        for movie_id, tmdb_id, imdb_id, release_date, budget_usd in movies:
            with conn.cursor() as cur:
                trailers = get_trailers_for_movie(cur, movie_id)

            stage = detect_stage(release_date, trailers, today)

            # Only search for a trailer on movies still progressing toward
            # release, and only once (until one's found) - keeps YouTube
            # quota usage to the small "active" subset, never the historical
            # corpus (see planning doc).
            if stage != "post_release" and not trailers and youtube_api_key and not youtube_limited:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT title FROM movies WHERE id = %s", (movie_id,))
                        title = cur.fetchone()[0]
                    found = search_trailer(title, release_date.year if release_date else None, youtube_api_key)
                    if found:
                        with conn.cursor() as cur:
                            insert_trailer(
                                cur,
                                movie_id,
                                found["video_id"],
                                f"https://www.youtube.com/watch?v={found['video_id']}",
                                "teaser" if "teaser" in found["title"].lower() else "trailer",
                                found["published_at"],
                            )
                        conn.commit()
                        with conn.cursor() as cur:
                            trailers = get_trailers_for_movie(cur, movie_id)
                        stage = detect_stage(release_date, trailers, today)
                except YouTubeQuotaExceeded:
                    youtube_limited = True
                    print("[stage-scan] YouTube quota exceeded - skipping trailer search for the rest of this run")
                except Exception as exc:
                    print(f"[stage-scan] error searching trailer for movie_id={movie_id}: {exc}")

            # Refresh stats for any known trailers (cheap - safe for the
            # whole active subset every run).
            if trailers and youtube_api_key and not youtube_limited:
                try:
                    stats_by_id = get_video_stats([t["external_id"] for t in trailers], youtube_api_key)
                    with conn.cursor() as cur:
                        for t in trailers:
                            stats = stats_by_id.get(t["external_id"])
                            if stats:
                                upsert_trailer_metrics(cur, t["id"], today, stats)
                    conn.commit()
                except YouTubeQuotaExceeded:
                    youtube_limited = True
                except Exception as exc:
                    print(f"[stage-scan] error fetching trailer stats for movie_id={movie_id}: {exc}")

            own_worldwide = None
            if stage == "post_release":
                with conn.cursor() as cur:
                    cur.execute("SELECT total_worldwide FROM box_office_totals WHERE movie_id = %s", (movie_id,))
                    row = cur.fetchone()
                    own_worldwide = row[0] if row else None

            with conn.cursor() as cur:
                verdict = compute_verdict(cur, movie_id, budget_usd, own_worldwide)
                upsert_verdict(cur, movie_id, stage, verdict)
            conn.commit()

            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        print(f"[stage-scan] done - {stage_counts}")
    finally:
        conn.close()


if __name__ == "__main__":
    stage_scan_flow()
