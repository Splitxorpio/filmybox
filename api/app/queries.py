from sqlalchemy import text
from sqlalchemy.engine import Connection


def _build_movie_filters(
    genre: str | None, year: int | None, search: str | None, upcoming: bool = False, released_only: bool = False
) -> tuple[str, dict]:
    clauses = []
    params: dict = {}
    if genre:
        clauses.append("m.genres @> ARRAY[:genre]::text[]")
        params["genre"] = genre
    if year:
        clauses.append("EXTRACT(YEAR FROM m.release_date) = :year")
        params["year"] = year
    if search:
        clauses.append("m.title ILIKE :search")
        params["search"] = f"%{search}%"
    if upcoming:
        clauses.append("m.release_date > CURRENT_DATE")
    if released_only:
        clauses.append("m.release_date <= CURRENT_DATE")
    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    return where_sql, params


def create_user(conn: Connection, email: str, password_hash: str) -> dict:
    row = conn.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:email, :password_hash) RETURNING id, email"),
        {"email": email, "password_hash": password_hash},
    ).mappings().first()
    conn.commit()
    return dict(row)


def get_user_by_email(conn: Connection, email: str) -> dict | None:
    row = conn.execute(
        text("SELECT id, email, password_hash FROM users WHERE email = :email"),
        {"email": email},
    ).mappings().first()
    return dict(row) if row else None


def list_movies(
    conn: Connection,
    genre: str | None,
    year: int | None,
    search: str | None,
    limit: int,
    offset: int,
    upcoming: bool = False,
    released_only: bool = False,
) -> tuple[int, list[dict]]:
    where_sql, params = _build_movie_filters(genre, year, search, upcoming, released_only)
    order_sql = "m.release_date ASC" if upcoming else "m.release_date DESC NULLS LAST"

    total = conn.execute(text(f"SELECT count(*) FROM movies m WHERE {where_sql}"), params).scalar_one()

    rows = (
        conn.execute(
            text(
                f"""
                SELECT m.id, m.title, m.release_date, m.genres, m.mpaa_rating, m.budget_usd,
                       m.poster_path, s.name AS studio_name, bot.total_worldwide
                FROM movies m
                LEFT JOIN studios s ON s.id = m.studio_id
                LEFT JOIN box_office_totals bot ON bot.movie_id = m.id
                WHERE {where_sql}
                ORDER BY {order_sql}
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )
    return total, rows


def get_movie(conn: Connection, movie_id: int) -> dict | None:
    row = conn.execute(
        text(
            """
            SELECT m.id, m.imdb_id, m.title, m.release_date, m.genres, m.runtime_minutes, m.mpaa_rating,
                   m.original_language, m.budget_usd, m.budget_confidence, m.poster_path,
                   s.id AS studio_id, s.name AS studio_name,
                   f.id AS franchise_id, f.name AS franchise_name
            FROM movies m
            LEFT JOIN studios s ON s.id = m.studio_id
            LEFT JOIN franchises f ON f.id = m.franchise_id
            WHERE m.id = :movie_id
            """
        ),
        {"movie_id": movie_id},
    ).mappings().first()
    return dict(row) if row else None


def get_movie_credits(conn: Connection, movie_id: int) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT p.id AS person_id, p.name, mc.role_type, mc.billing_order, mc.character_name
            FROM movie_credits mc
            JOIN people p ON p.id = mc.person_id
            WHERE mc.movie_id = :movie_id
            ORDER BY
                CASE mc.role_type
                    WHEN 'director' THEN 0
                    WHEN 'writer' THEN 1
                    WHEN 'producer' THEN 2
                    WHEN 'actor' THEN 3
                END,
                mc.billing_order NULLS LAST
            """
        ),
        {"movie_id": movie_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def get_primary_credits(conn: Connection, movie_id: int) -> tuple[int | None, int | None]:
    """(primary_director_id, lead_actor_id) - the two person ids
    gbt_predictor.py needs for its prior-avg-ROI lookups, without pulling
    the full credits list get_movie_credits already returns.
    """
    director_id = conn.execute(
        text(
            """
            SELECT person_id FROM movie_credits
            WHERE movie_id = :movie_id AND role_type = 'director'
            ORDER BY billing_order NULLS LAST LIMIT 1
            """
        ),
        {"movie_id": movie_id},
    ).scalar_one_or_none()
    actor_id = conn.execute(
        text(
            """
            SELECT person_id FROM movie_credits
            WHERE movie_id = :movie_id AND role_type = 'actor'
            ORDER BY billing_order NULLS LAST LIMIT 1
            """
        ),
        {"movie_id": movie_id},
    ).scalar_one_or_none()
    return director_id, actor_id


def get_box_office(conn: Connection, movie_id: int) -> tuple[dict | None, list[dict]]:
    totals = conn.execute(
        text(
            """
            SELECT opening_weekend_domestic, total_domestic, total_international, total_worldwide
            FROM box_office_totals
            WHERE movie_id = :movie_id
            """
        ),
        {"movie_id": movie_id},
    ).mappings().first()

    weekly = conn.execute(
        text(
            """
            SELECT weekend_number, weekend_gross, theater_count
            FROM box_office_weekly
            WHERE movie_id = :movie_id
            ORDER BY weekend_number
            """
        ),
        {"movie_id": movie_id},
    ).mappings().all()

    return (dict(totals) if totals else None), [dict(row) for row in weekly]


def get_comps(conn: Connection, movie_id: int, limit: int) -> list[dict]:
    """Heuristic comps: shared genres + shared director/cast, weighted and ranked.

    Rewards exact-match signals (same director/actor) that the embedding-based
    get_comps_by_embedding won't necessarily surface - the two are
    complementary, not redundant (see planning doc).
    """
    rows = conn.execute(
        text(
            """
            WITH base AS (
                SELECT genres FROM movies WHERE id = :movie_id
            ),
            base_people AS (
                SELECT person_id, role_type FROM movie_credits WHERE movie_id = :movie_id
            )
            SELECT
                m.id AS movie_id,
                m.title,
                m.release_date,
                ARRAY(
                    SELECT unnest(m.genres) INTERSECT SELECT unnest(base.genres)
                ) AS shared_genres,
                (
                    cardinality(ARRAY(SELECT unnest(m.genres) INTERSECT SELECT unnest(base.genres)))
                    + COALESCE(director_match.cnt, 0) * 3
                    + COALESCE(actor_match.cnt, 0)
                ) AS score
            FROM movies m, base
            LEFT JOIN LATERAL (
                SELECT count(*) AS cnt FROM movie_credits mc
                WHERE mc.movie_id = m.id AND mc.role_type = 'director'
                  AND mc.person_id IN (SELECT person_id FROM base_people WHERE role_type = 'director')
            ) director_match ON true
            LEFT JOIN LATERAL (
                SELECT count(*) AS cnt FROM movie_credits mc
                WHERE mc.movie_id = m.id AND mc.role_type = 'actor'
                  AND mc.person_id IN (SELECT person_id FROM base_people WHERE role_type = 'actor')
            ) actor_match ON true
            WHERE m.id != :movie_id
              AND m.genres && base.genres
            ORDER BY score DESC, m.release_date DESC
            LIMIT :limit
            """
        ),
        {"movie_id": movie_id, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


def get_comps_by_embedding(conn: Connection, movie_id: int, limit: int) -> list[dict]:
    """Embedding-based comps via pgvector cosine distance (nomic-embed-text-v1.5,
    see prefect-worker/flows/build_embeddings.py). Surfaces broader style/tone
    similarity the heuristic's exact-match scoring can miss - e.g. Get Out's
    top embedding matches are other low-budget elevated-horror films, not just
    Jordan Peele's own movies specifically.
    """
    rows = conn.execute(
        text(
            """
            SELECT m.id AS movie_id, m.title, m.release_date,
                   (me2.embedding <=> me1.embedding) AS distance
            FROM movie_embeddings me1
            JOIN movie_embeddings me2 ON me2.movie_id != me1.movie_id
            JOIN movies m ON m.id = me2.movie_id
            WHERE me1.movie_id = :movie_id
            ORDER BY distance ASC
            LIMIT :limit
            """
        ),
        {"movie_id": movie_id, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


def get_critic_scores(conn: Connection, movie_id: int) -> dict | None:
    row = conn.execute(
        text(
            """
            SELECT imdb_rating, imdb_votes, rotten_tomatoes_pct, metacritic_score,
                   tmdb_vote_average, tmdb_vote_count
            FROM critic_scores
            WHERE movie_id = :movie_id
            """
        ),
        {"movie_id": movie_id},
    ).mappings().first()
    return dict(row) if row else None


def upsert_critic_scores(conn: Connection, movie_id: int, scores: dict) -> None:
    conn.execute(
        text(
            """
            INSERT INTO critic_scores (movie_id, imdb_rating, imdb_votes, rotten_tomatoes_pct, metacritic_score)
            VALUES (:movie_id, :imdb_rating, :imdb_votes, :rotten_tomatoes_pct, :metacritic_score)
            ON CONFLICT (movie_id) DO UPDATE SET
                imdb_rating = EXCLUDED.imdb_rating,
                imdb_votes = EXCLUDED.imdb_votes,
                rotten_tomatoes_pct = EXCLUDED.rotten_tomatoes_pct,
                metacritic_score = EXCLUDED.metacritic_score,
                fetched_at = now()
            """
        ),
        {"movie_id": movie_id, **scores},
    )
    conn.commit()


_STAGE_RANK_SQL = """
    CASE stage
        WHEN 'announcement' THEN 1
        WHEN 'teaser' THEN 2
        WHEN 'trailer' THEN 3
        WHEN 'pre_release' THEN 4
        WHEN 'post_release' THEN 5
    END
"""


def get_sentiment_for_prediction(conn: Connection, movie_id: int) -> dict:
    """Bluesky (post_release stage) + whichever single youtube_comments
    snapshot exists for this movie - mirrors prefect-worker/db.py's
    get_movies_for_training() sentiment joins exactly (same column names),
    so gbt_predictor.py can build the same features train_model.py trained
    on. LATERAL for youtube_comments for the same reason as the training
    query: (movie_id, source) alone isn't covered by the
    (movie_id, stage, source) unique constraint, so a plain join could in
    principle return more than one row.
    """
    row = conn.execute(
        text(
            """
            SELECT
                bs.sentiment_score AS bluesky_sentiment_score, bs.volume AS bluesky_volume,
                bs.avg_engagement_score AS bluesky_avg_engagement,
                ys.sentiment_score AS youtube_sentiment_score, ys.volume AS youtube_volume,
                ys.avg_engagement_score AS youtube_avg_engagement
            FROM (SELECT :movie_id AS id) m
            LEFT JOIN sentiment_snapshots bs
                ON bs.movie_id = m.id AND bs.source = 'bluesky' AND bs.stage = 'post_release'
            LEFT JOIN LATERAL (
                SELECT sentiment_score, volume, avg_engagement_score
                FROM sentiment_snapshots
                WHERE movie_id = m.id AND source = 'youtube_comments'
                ORDER BY snapshot_date DESC LIMIT 1
            ) ys ON true
            """
        ),
        {"movie_id": movie_id},
    ).mappings().first()
    return dict(row) if row else {}


def get_sentiment(conn: Connection, movie_id: int) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT source, stage, snapshot_date, sentiment_score, volume, avg_engagement_score
            FROM sentiment_snapshots
            WHERE movie_id = :movie_id
            ORDER BY source, snapshot_date DESC
            """
        ),
        {"movie_id": movie_id},
    ).mappings().all()
    return [dict(row) for row in rows]


def get_verdicts(conn: Connection, movie_id: int) -> list[dict]:
    rows = conn.execute(
        text(
            f"""
            SELECT stage, computed_at, comp_count, roi_multiple_p25, roi_multiple_p50,
                   roi_multiple_p75, verdict_bucket, comp_movie_ids, actual_roi_multiple,
                   actual_bucket, method
            FROM verdicts
            WHERE movie_id = :movie_id
            ORDER BY {_STAGE_RANK_SQL} ASC
            """
        ),
        {"movie_id": movie_id},
    ).mappings().all()
    return [dict(row) for row in rows]
