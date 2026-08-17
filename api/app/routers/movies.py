from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from datetime import datetime, timezone

from app import gbt_predictor, queries
from app.cache import cache_get, cache_set
from app.config import settings
from app.db import get_db
from app.omdb_client import OMDbRateLimited, fetch_critic_scores
from app.schemas import (
    CompOut,
    CriticScoresOut,
    FranchiseOut,
    LivePredictionOut,
    MovieDetail,
    MovieListResponse,
    MovieSummary,
    SentimentSnapshotOut,
    StudioOut,
    VerdictOut,
)

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("", response_model=MovieListResponse)
def list_movies(
    genre: str | None = None,
    year: int | None = None,
    search: str | None = None,
    upcoming: bool = False,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_db),
):
    cache_key = f"movies:{genre}:{year}:{search}:{upcoming}:{limit}:{offset}"
    cached = cache_get(cache_key)
    if cached is not None:
        return MovieListResponse(**cached)

    total, rows = queries.list_movies(conn, genre, year, search, limit, offset, upcoming)
    items = [
        MovieSummary(
            id=row["id"],
            title=row["title"],
            release_date=row["release_date"],
            genres=row["genres"],
            mpaa_rating=row["mpaa_rating"],
            budget_usd=row["budget_usd"],
            studio_name=row["studio_name"],
            total_worldwide=row["total_worldwide"],
        )
        for row in rows
    ]
    result = MovieListResponse(total=total, limit=limit, offset=offset, items=items)
    cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
    return result


def _get_or_fetch_critic_scores(conn: Connection, movie_id: int, imdb_id: str | None) -> CriticScoresOut | None:
    cached = queries.get_critic_scores(conn, movie_id)
    if cached is not None:
        return CriticScoresOut(**cached)

    if not settings.omdb_api_key or not imdb_id:
        return None

    try:
        scores = fetch_critic_scores(imdb_id, settings.omdb_api_key)
    except OMDbRateLimited:
        return None
    except Exception:
        # Network hiccup, malformed response, etc. - the rest of the movie
        # detail response must still succeed regardless.
        return None

    if scores is None:
        return None

    queries.upsert_critic_scores(conn, movie_id, scores)
    return CriticScoresOut(**scores)


@router.get("/{movie_id}", response_model=MovieDetail)
def get_movie(movie_id: int, conn: Connection = Depends(get_db)):
    movie = queries.get_movie(conn, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    credits = queries.get_movie_credits(conn, movie_id)
    totals, weekly = queries.get_box_office(conn, movie_id)
    critic_scores = _get_or_fetch_critic_scores(conn, movie_id, movie["imdb_id"])

    return MovieDetail(
        id=movie["id"],
        title=movie["title"],
        release_date=movie["release_date"],
        genres=movie["genres"],
        runtime_minutes=movie["runtime_minutes"],
        mpaa_rating=movie["mpaa_rating"],
        original_language=movie["original_language"],
        budget_usd=movie["budget_usd"],
        budget_confidence=movie["budget_confidence"],
        studio=StudioOut(id=movie["studio_id"], name=movie["studio_name"]) if movie["studio_id"] else None,
        franchise=(
            FranchiseOut(id=movie["franchise_id"], name=movie["franchise_name"]) if movie["franchise_id"] else None
        ),
        credits=credits,
        box_office_totals=totals,
        box_office_weekly=weekly,
        critic_scores=critic_scores,
    )


@router.get("/{movie_id}/comps", response_model=list[CompOut])
def get_comps(
    movie_id: int,
    limit: int = Query(10, ge=1, le=50),
    method: Literal["embedding", "heuristic"] = "embedding",
    conn: Connection = Depends(get_db),
):
    cache_key = f"comps:{movie_id}:{method}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    if queries.get_movie(conn, movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if method == "embedding":
        result = queries.get_comps_by_embedding(conn, movie_id, limit)
    else:
        result = queries.get_comps(conn, movie_id, limit)

    cache_set(cache_key, [CompOut(**row).model_dump(mode="json") for row in result], ttl_seconds=900)
    return result


@router.get("/{movie_id}/verdicts", response_model=list[VerdictOut])
def get_verdicts(movie_id: int, conn: Connection = Depends(get_db)):
    if queries.get_movie(conn, movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return queries.get_verdicts(conn, movie_id)


@router.get("/{movie_id}/sentiment", response_model=list[SentimentSnapshotOut])
def get_sentiment(movie_id: int, conn: Connection = Depends(get_db)):
    if queries.get_movie(conn, movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    return queries.get_sentiment(conn, movie_id)


@router.get("/{movie_id}/predict", response_model=LivePredictionOut)
def predict(movie_id: int, conn: Connection = Depends(get_db)):
    """Live prediction (gbt_predictor.METHOD), computed on the spot rather
    than read from verdicts - covers movies the last batch train_model.py
    run hasn't reached yet (see planning doc's Model Serving section).
    """
    cache_key = f"predict:{movie_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return LivePredictionOut(**cached)

    movie = queries.get_movie(conn, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    director_id, actor_id = queries.get_primary_credits(conn, movie_id)
    critic_scores = queries.get_critic_scores(conn, movie_id)
    sentiment = queries.get_sentiment_for_prediction(conn, movie_id)

    result = gbt_predictor.predict_verdict(movie, director_id, actor_id, critic_scores, sentiment)
    now = datetime.now(timezone.utc)
    if result is None:
        response = LivePredictionOut(
            roi_multiple_p25=None,
            roi_multiple_p50=None,
            roi_multiple_p75=None,
            verdict_bucket=None,
            method=gbt_predictor.METHOD,
            computed_at=now,
            reason="no budget",
        )
    else:
        response = LivePredictionOut(**result, computed_at=now)

    cache_set(cache_key, response.model_dump(mode="json"), ttl_seconds=3600)
    return response
