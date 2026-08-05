from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.engine import Connection

from app import queries
from app.config import settings
from app.db import get_db
from app.omdb_client import OMDbRateLimited, fetch_critic_scores
from app.schemas import (
    CompOut,
    CriticScoresOut,
    FranchiseOut,
    MovieDetail,
    MovieListResponse,
    MovieSummary,
    StudioOut,
)

router = APIRouter(prefix="/movies", tags=["movies"])


@router.get("", response_model=MovieListResponse)
def list_movies(
    genre: str | None = None,
    year: int | None = None,
    search: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: Connection = Depends(get_db),
):
    total, rows = queries.list_movies(conn, genre, year, search, limit, offset)
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
    return MovieListResponse(total=total, limit=limit, offset=offset, items=items)


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
    if queries.get_movie(conn, movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if method == "embedding":
        return queries.get_comps_by_embedding(conn, movie_id, limit)
    return queries.get_comps(conn, movie_id, limit)
