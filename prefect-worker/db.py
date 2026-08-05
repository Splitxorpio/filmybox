import os

import psycopg
from pgvector.psycopg import register_vector


def get_connection() -> psycopg.Connection:
    # DATABASE_URL uses the SQLAlchemy-style "postgresql+psycopg://" dialect
    # prefix; psycopg's native connect wants a plain "postgresql://" DSN.
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(dsn)
    register_vector(conn)
    return conn


def upsert_studio(cur, tmdb_company_id: int, name: str) -> int:
    cur.execute(
        """
        INSERT INTO studios (tmdb_company_id, name)
        VALUES (%s, %s)
        ON CONFLICT (tmdb_company_id) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (tmdb_company_id, name),
    )
    return cur.fetchone()[0]


def upsert_franchise(cur, tmdb_collection_id: int, name: str) -> int:
    cur.execute(
        """
        INSERT INTO franchises (tmdb_collection_id, name)
        VALUES (%s, %s)
        ON CONFLICT (tmdb_collection_id) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (tmdb_collection_id, name),
    )
    return cur.fetchone()[0]


def upsert_movie(cur, movie: dict) -> int:
    cur.execute(
        """
        INSERT INTO movies (
            tmdb_id, imdb_id, title, release_date, genres, runtime_minutes,
            mpaa_rating, original_language, budget_usd, budget_confidence,
            franchise_id, studio_id
        )
        VALUES (
            %(tmdb_id)s, %(imdb_id)s, %(title)s, %(release_date)s, %(genres)s,
            %(runtime_minutes)s, %(mpaa_rating)s, %(original_language)s,
            %(budget_usd)s, %(budget_confidence)s, %(franchise_id)s, %(studio_id)s
        )
        ON CONFLICT (tmdb_id) DO UPDATE SET
            imdb_id = EXCLUDED.imdb_id,
            title = EXCLUDED.title,
            release_date = EXCLUDED.release_date,
            genres = EXCLUDED.genres,
            runtime_minutes = EXCLUDED.runtime_minutes,
            mpaa_rating = EXCLUDED.mpaa_rating,
            original_language = EXCLUDED.original_language,
            budget_usd = EXCLUDED.budget_usd,
            budget_confidence = EXCLUDED.budget_confidence,
            franchise_id = EXCLUDED.franchise_id,
            studio_id = EXCLUDED.studio_id,
            updated_at = now()
        RETURNING id
        """,
        movie,
    )
    return cur.fetchone()[0]


def upsert_person(cur, tmdb_id: int, name: str, imdb_id: str | None, birth_year: int | None) -> int:
    cur.execute(
        """
        INSERT INTO people (tmdb_id, imdb_id, name, birth_year)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (tmdb_id) DO UPDATE SET
            imdb_id = EXCLUDED.imdb_id,
            name = EXCLUDED.name,
            birth_year = EXCLUDED.birth_year
        RETURNING id
        """,
        (tmdb_id, imdb_id, name, birth_year),
    )
    return cur.fetchone()[0]


def upsert_movie_credit(
    cur,
    movie_id: int,
    person_id: int,
    role_type: str,
    billing_order: int | None,
    character_name: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO movie_credits (movie_id, person_id, role_type, billing_order, character_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (movie_id, person_id, role_type) DO UPDATE SET
            billing_order = EXCLUDED.billing_order,
            character_name = EXCLUDED.character_name
        """,
        (movie_id, person_id, role_type, billing_order, character_name),
    )


def get_movies_missing_box_office(cur) -> list[tuple[int, str]]:
    """(movie_id, imdb_id) for movies not yet scraped from Box Office Mojo."""
    cur.execute(
        """
        SELECT m.id, m.imdb_id
        FROM movies m
        LEFT JOIN box_office_totals bot ON bot.movie_id = m.id
        WHERE m.imdb_id IS NOT NULL AND bot.movie_id IS NULL
        """
    )
    return cur.fetchall()


def upsert_box_office_totals(
    cur,
    movie_id: int,
    domestic: int | None,
    international: int | None,
    worldwide: int | None,
    opening_weekend_domestic: int | None,
    source: str,
) -> None:
    cur.execute(
        """
        INSERT INTO box_office_totals (
            movie_id, opening_weekend_domestic, total_domestic, total_international,
            total_worldwide, source
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (movie_id) DO UPDATE SET
            opening_weekend_domestic = EXCLUDED.opening_weekend_domestic,
            total_domestic = EXCLUDED.total_domestic,
            total_international = EXCLUDED.total_international,
            total_worldwide = EXCLUDED.total_worldwide,
            source = EXCLUDED.source,
            last_updated = now()
        """,
        (movie_id, opening_weekend_domestic, domestic, international, worldwide, source),
    )


def upsert_box_office_weekly(
    cur,
    movie_id: int,
    weekend_number: int,
    weekend_gross: int | None,
    theater_count: int | None,
    source: str,
) -> None:
    cur.execute(
        """
        INSERT INTO box_office_weekly (movie_id, weekend_number, weekend_gross, theater_count, source)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (movie_id, weekend_number) DO UPDATE SET
            weekend_gross = EXCLUDED.weekend_gross,
            theater_count = EXCLUDED.theater_count,
            source = EXCLUDED.source,
            last_updated = now()
        """,
        (movie_id, weekend_number, weekend_gross, theater_count, source),
    )


def get_movies_missing_embeddings(cur) -> list[dict]:
    cur.execute(
        """
        SELECT m.id, m.title, m.release_date, m.genres, m.budget_usd, s.name AS studio_name
        FROM movies m
        LEFT JOIN studios s ON s.id = m.studio_id
        LEFT JOIN movie_embeddings me ON me.movie_id = m.id
        WHERE me.movie_id IS NULL
        """
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_credits_for_movies(cur, movie_ids: list[int]) -> dict[int, list[dict]]:
    """movie_id -> ordered list of {name, role_type, billing_order}."""
    if not movie_ids:
        return {}
    cur.execute(
        """
        SELECT mc.movie_id, p.name, mc.role_type, mc.billing_order
        FROM movie_credits mc
        JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = ANY(%s)
        ORDER BY mc.movie_id, mc.billing_order NULLS LAST
        """,
        (movie_ids,),
    )
    by_movie: dict[int, list[dict]] = {}
    for movie_id, name, role_type, billing_order in cur.fetchall():
        by_movie.setdefault(movie_id, []).append(
            {"name": name, "role_type": role_type, "billing_order": billing_order}
        )
    return by_movie


def upsert_movie_embedding(cur, movie_id: int, embedding: list[float], model_version: str) -> None:
    cur.execute(
        """
        INSERT INTO movie_embeddings (movie_id, embedding, model_version, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (movie_id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            model_version = EXCLUDED.model_version,
            updated_at = now()
        """,
        (movie_id, embedding, model_version),
    )


def get_movies_missing_critic_scores(cur, limit: int) -> list[tuple[int, str]]:
    """(movie_id, imdb_id), most recently released first - prioritizes
    movies most likely to be viewed soon on the dashboard.
    """
    cur.execute(
        """
        SELECT m.id, m.imdb_id
        FROM movies m
        LEFT JOIN critic_scores cs ON cs.movie_id = m.id
        WHERE m.imdb_id IS NOT NULL AND cs.movie_id IS NULL
        ORDER BY m.release_date DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()


def upsert_critic_scores(cur, movie_id: int, scores: dict) -> None:
    cur.execute(
        """
        INSERT INTO critic_scores (movie_id, imdb_rating, imdb_votes, rotten_tomatoes_pct, metacritic_score)
        VALUES (%(movie_id)s, %(imdb_rating)s, %(imdb_votes)s, %(rotten_tomatoes_pct)s, %(metacritic_score)s)
        ON CONFLICT (movie_id) DO UPDATE SET
            imdb_rating = EXCLUDED.imdb_rating,
            imdb_votes = EXCLUDED.imdb_votes,
            rotten_tomatoes_pct = EXCLUDED.rotten_tomatoes_pct,
            metacritic_score = EXCLUDED.metacritic_score,
            fetched_at = now()
        """,
        {"movie_id": movie_id, **scores},
    )


def get_recent_movies(cur, days: int = 90) -> list[tuple[int, int, str]]:
    """(movie_id, tmdb_id, imdb_id) for movies released within the last N
    days (or in the future - upcoming releases included). Older movies'
    RT/Metacritic gaps are inherent to OMDb's own data (confirmed by direct
    spot-check), not something a refresh fixes, so this stays narrow.
    """
    cur.execute(
        """
        SELECT id, tmdb_id, imdb_id
        FROM movies
        WHERE release_date >= CURRENT_DATE - make_interval(days => %s)
          AND tmdb_id IS NOT NULL AND imdb_id IS NOT NULL
        ORDER BY release_date DESC
        """,
        (days,),
    )
    return cur.fetchall()


def ensure_critic_scores_row(cur, movie_id: int) -> None:
    cur.execute(
        "INSERT INTO critic_scores (movie_id) VALUES (%s) ON CONFLICT (movie_id) DO NOTHING",
        (movie_id,),
    )


def update_tmdb_votes(cur, movie_id: int, vote_average: float | None, vote_count: int | None) -> None:
    cur.execute(
        "UPDATE critic_scores SET tmdb_vote_average = %s, tmdb_vote_count = %s WHERE movie_id = %s",
        (vote_average, vote_count, movie_id),
    )
