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


def get_movies_missing_budget(cur) -> list[tuple[int, str]]:
    """(movie_id, imdb_id) for movies with no budget_usd - candidates for
    the Wikidata backfill (see wikidata_client.py / budget_backfill.py).
    """
    cur.execute(
        """
        SELECT id, imdb_id FROM movies
        WHERE budget_usd IS NULL AND imdb_id IS NOT NULL
        """
    )
    return cur.fetchall()


def get_movies_missing_budget_titles(cur) -> list[tuple[int, str, object]]:
    """(movie_id, title, release_date) for the same population as
    get_movies_missing_budget - a title+year variant for budget_social_backfill.py,
    which searches by title rather than looking up by imdb_id.
    """
    cur.execute(
        """
        SELECT id, title, release_date FROM movies
        WHERE budget_usd IS NULL
        """
    )
    return cur.fetchall()


def update_movie_budget(cur, movie_id: int, budget_usd: int, confidence: str = "estimated") -> None:
    cur.execute(
        """
        UPDATE movies SET budget_usd = %s, budget_confidence = %s, updated_at = now()
        WHERE id = %s
        """,
        (budget_usd, confidence, movie_id),
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


def get_budgeted_movies_missing_critic_scores(cur, limit: int) -> list[tuple[int, str]]:
    """(movie_id, imdb_id), oldest released first, restricted to movies with
    a budget. Separate purpose from get_movies_missing_critic_scores (which
    prioritizes recency for dashboard freshness): this backfills historical
    coverage specifically for GBT training, where the existing recency-first
    trickle left 0 pre-2021-07-29 movies with a critic score (see planning
    doc's GBT v2 section) - oldest-first directly closes that gap.
    """
    cur.execute(
        """
        SELECT m.id, m.imdb_id
        FROM movies m
        LEFT JOIN critic_scores cs ON cs.movie_id = m.id
        WHERE m.imdb_id IS NOT NULL AND cs.movie_id IS NULL
          AND m.budget_usd IS NOT NULL AND m.budget_usd > 0
        ORDER BY m.release_date ASC NULLS LAST
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


_STAGE_RANK_SQL = """
    CASE stage
        WHEN 'post_release' THEN 5
        WHEN 'pre_release' THEN 4
        WHEN 'trailer' THEN 3
        WHEN 'teaser' THEN 2
        WHEN 'announcement' THEN 1
    END
"""


def get_movies_needing_stage_check(cur) -> list[tuple[int, int, str, object, object]]:
    """(movie_id, tmdb_id, imdb_id, release_date, budget_usd) for movies with
    no verdict yet, or whose furthest-reached stage isn't post_release yet.
    Doubles as both the one-time historical backfill (first run) and the
    ongoing daily incremental scan, since almost all historical movies land
    straight in post_release and are never revisited after that.
    """
    cur.execute(
        f"""
        SELECT m.id, m.tmdb_id, m.imdb_id, m.release_date, m.budget_usd
        FROM movies m
        LEFT JOIN LATERAL (
            SELECT stage FROM verdicts v WHERE v.movie_id = m.id
            ORDER BY {_STAGE_RANK_SQL} DESC LIMIT 1
        ) latest ON true
        WHERE latest.stage IS NULL OR latest.stage != 'post_release'
        """
    )
    return cur.fetchall()


def get_trailers_for_movie(cur, movie_id: int) -> list[dict]:
    cur.execute(
        "SELECT id, external_id, trailer_type, publish_date FROM trailers WHERE movie_id = %s",
        (movie_id,),
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def insert_trailer(
    cur,
    movie_id: int,
    external_id: str,
    url: str,
    trailer_type: str,
    publish_date,
) -> int:
    cur.execute(
        """
        INSERT INTO trailers (movie_id, platform, external_id, url, trailer_type, publish_date)
        VALUES (%s, 'youtube', %s, %s, %s, %s)
        RETURNING id
        """,
        (movie_id, external_id, url, trailer_type, publish_date),
    )
    return cur.fetchone()[0]


def upsert_trailer_metrics(cur, trailer_id: int, snapshot_date, stats: dict) -> None:
    cur.execute(
        """
        INSERT INTO trailer_metrics (trailer_id, snapshot_date, view_count, like_count, comment_count)
        VALUES (%(trailer_id)s, %(snapshot_date)s, %(view_count)s, %(like_count)s, %(comment_count)s)
        ON CONFLICT (trailer_id, snapshot_date) DO UPDATE SET
            view_count = EXCLUDED.view_count,
            like_count = EXCLUDED.like_count,
            comment_count = EXCLUDED.comment_count
        """,
        {"trailer_id": trailer_id, "snapshot_date": snapshot_date, **stats},
    )


def get_comps_for_verdict(cur, movie_id: int, limit: int) -> list[tuple[int, object, object]]:
    """(comp_movie_id, budget_usd, total_worldwide) for the top-k embedding
    comps, same <=> cosine-distance query as api/app/queries.py's
    get_comps_by_embedding - duplicated per the established cross-service
    pattern (api/ and prefect-worker/ already share no code).
    """
    cur.execute(
        """
        SELECT m.id, m.budget_usd, bot.total_worldwide
        FROM movie_embeddings me1
        JOIN movie_embeddings me2 ON me2.movie_id != me1.movie_id
        JOIN movies m ON m.id = me2.movie_id
        LEFT JOIN box_office_totals bot ON bot.movie_id = m.id
        WHERE me1.movie_id = %s
        ORDER BY (me2.embedding <=> me1.embedding) ASC
        LIMIT %s
        """,
        (movie_id, limit),
    )
    return cur.fetchall()


def get_movies_for_training(cur) -> list[dict]:
    """All movies with a budget, plus everything needed to build GBT features:
    box office (nullable - only present for released movies), studio/franchise
    ids, director/lead-actor person ids (first-billed of each role), critic
    scores (nullable - only present for movies OMDb/TMDb trickle has reached).
    """
    cur.execute(
        """
        SELECT
            m.id, m.release_date, m.genres, m.runtime_minutes, m.mpaa_rating,
            m.original_language, m.budget_usd, m.studio_id, m.franchise_id,
            bot.total_worldwide,
            cs.imdb_rating, cs.imdb_votes, cs.rotten_tomatoes_pct, cs.metacritic_score,
            cs.tmdb_vote_average, cs.tmdb_vote_count,
            (SELECT array_agg(mc.person_id ORDER BY mc.billing_order NULLS LAST)
             FROM movie_credits mc WHERE mc.movie_id = m.id AND mc.role_type = 'director') AS director_ids,
            (SELECT mc.person_id FROM movie_credits mc
             WHERE mc.movie_id = m.id AND mc.role_type = 'actor'
             ORDER BY mc.billing_order NULLS LAST LIMIT 1) AS lead_actor_id
        FROM movies m
        LEFT JOIN box_office_totals bot ON bot.movie_id = m.id
        LEFT JOIN critic_scores cs ON cs.movie_id = m.id
        WHERE m.budget_usd IS NOT NULL AND m.budget_usd > 0
        ORDER BY m.release_date NULLS LAST
        """
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_latest_stages(cur) -> dict[int, str]:
    """movie_id -> furthest-reached stage, for every movie with a verdict row."""
    cur.execute(
        f"""
        SELECT movie_id, stage FROM (
            SELECT movie_id, stage,
                   ROW_NUMBER() OVER (PARTITION BY movie_id ORDER BY {_STAGE_RANK_SQL} DESC) AS rn
            FROM verdicts
        ) ranked WHERE rn = 1
        """
    )
    return dict(cur.fetchall())


def get_released_movies_missing_trailer(cur, limit: int) -> list[tuple[int, str, object]]:
    """(movie_id, title, release_date) for already-released movies with both
    budget_usd and a box_office_totals row (the exact population
    get_movies_for_training() trains on) that have no trailers row yet.
    Most-recent-release first: recent movies are far more likely to have a
    real trailer indexed on YouTube under a title search (older/obscure
    titles frequently return unrelated or fan-made results), so this order
    maximizes hit rate per unit of quota spent - separate purpose from
    stage_scan.py, which never touches this already-released population at
    all (see planning doc).
    """
    cur.execute(
        """
        SELECT m.id, m.title, m.release_date
        FROM movies m
        JOIN box_office_totals bot ON bot.movie_id = m.id
        LEFT JOIN trailers t ON t.movie_id = m.id
        WHERE m.budget_usd IS NOT NULL AND m.budget_usd > 0
          AND m.release_date IS NOT NULL AND m.release_date <= CURRENT_DATE
          AND t.movie_id IS NULL
        ORDER BY m.release_date DESC
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()


def upsert_verdict(cur, movie_id: int, stage: str, verdict: dict, method: str = "comp_heuristic_v1") -> None:
    cur.execute(
        """
        INSERT INTO verdicts (
            movie_id, stage, method, comp_count, roi_multiple_p25, roi_multiple_p50, roi_multiple_p75,
            verdict_bucket, comp_movie_ids, actual_roi_multiple, actual_bucket
        )
        VALUES (
            %(movie_id)s, %(stage)s, %(method)s, %(comp_count)s, %(roi_multiple_p25)s, %(roi_multiple_p50)s,
            %(roi_multiple_p75)s, %(verdict_bucket)s, %(comp_movie_ids)s, %(actual_roi_multiple)s,
            %(actual_bucket)s
        )
        ON CONFLICT (movie_id, stage, method) DO UPDATE SET
            computed_at = now(),
            comp_count = EXCLUDED.comp_count,
            roi_multiple_p25 = EXCLUDED.roi_multiple_p25,
            roi_multiple_p50 = EXCLUDED.roi_multiple_p50,
            roi_multiple_p75 = EXCLUDED.roi_multiple_p75,
            verdict_bucket = EXCLUDED.verdict_bucket,
            comp_movie_ids = EXCLUDED.comp_movie_ids,
            actual_roi_multiple = EXCLUDED.actual_roi_multiple,
            actual_bucket = EXCLUDED.actual_bucket
        """,
        {"movie_id": movie_id, "stage": stage, "method": method, **verdict},
    )


def get_upcoming_movies_for_sentiment(cur) -> list[dict]:
    """(id, title, release_date) for every movie not yet released - the full
    set, not just ones missing a snapshot, since pre_release buzz is
    expected to change run over run and upsert_sentiment_snapshot() just
    refreshes the row in place. Small population (unreleased titles only),
    so no LIMIT - the reddit_buzz_upcoming flow is meant to run eagerly/
    frequently against this whole set.
    """
    cur.execute(
        """
        SELECT id, title, release_date
        FROM movies
        WHERE release_date IS NOT NULL AND release_date > CURRENT_DATE
        ORDER BY release_date ASC
        """
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_movies_for_reddit_backfill(cur, limit: int) -> list[dict]:
    """(id, title, release_date) for released movies with a budget AND a
    box_office_totals row - mirrors get_movies_for_training()'s population
    (minus the budget-only relaxation) so Reddit sentiment lands on exactly
    the movies that matter for GBT features, not the whole catalog. Oldest-
    first, same reasoning as get_budgeted_movies_missing_critic_scores: closes
    historical coverage gaps first rather than re-trickling recent releases
    that other sources already cover well. Excludes movies that already have
    a post_release reddit snapshot.
    """
    cur.execute(
        """
        SELECT m.id, m.title, m.release_date
        FROM movies m
        JOIN box_office_totals bot ON bot.movie_id = m.id
        LEFT JOIN sentiment_snapshots ss
            ON ss.movie_id = m.id AND ss.stage = 'post_release' AND ss.source = 'reddit'
        WHERE m.budget_usd IS NOT NULL AND m.budget_usd > 0
          AND m.release_date IS NOT NULL AND m.release_date <= CURRENT_DATE
          AND ss.movie_id IS NULL
        ORDER BY m.release_date ASC
        LIMIT %s
        """,
        (limit,),
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_movies_needing_comment_sentiment(cur, limit: int) -> list[dict]:
    """(movie_id, title, external_id, trailer_type) for the primary trailer
    (sequence_number=1) of every movie that has one, regardless of release
    status - trailer reactions are relevant whether the movie has come out
    yet or not, unlike Reddit's released-vs-upcoming split. Excludes trailers
    that already have a youtube_comments snapshot for their own stage.
    """
    cur.execute(
        """
        SELECT m.id AS movie_id, m.title, t.external_id, t.trailer_type
        FROM movies m
        JOIN trailers t ON t.movie_id = m.id AND t.sequence_number = 1
        LEFT JOIN sentiment_snapshots ss
            ON ss.movie_id = m.id AND ss.stage = t.trailer_type AND ss.source = 'youtube_comments'
        WHERE ss.movie_id IS NULL
        LIMIT %s
        """,
        (limit,),
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_movies_for_bluesky_backfill(cur, limit: int) -> list[dict]:
    """Same population/reasoning as get_movies_for_reddit_backfill, keyed to
    source='bluesky' instead - independent coverage tracking per source.
    """
    cur.execute(
        """
        SELECT m.id, m.title, m.release_date
        FROM movies m
        JOIN box_office_totals bot ON bot.movie_id = m.id
        LEFT JOIN sentiment_snapshots ss
            ON ss.movie_id = m.id AND ss.stage = 'post_release' AND ss.source = 'bluesky'
        WHERE m.budget_usd IS NOT NULL AND m.budget_usd > 0
          AND m.release_date IS NOT NULL AND m.release_date <= CURRENT_DATE
          AND ss.movie_id IS NULL
        ORDER BY m.release_date ASC
        LIMIT %s
        """,
        (limit,),
    )
    columns = [desc.name for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def upsert_sentiment_snapshot(
    cur,
    movie_id: int,
    stage: str,
    sentiment_score: float | None,
    volume: int,
    avg_engagement_score: float | None,
    raw_sample_ids: list[str],
    source: str = "reddit",
) -> None:
    cur.execute(
        """
        INSERT INTO sentiment_snapshots (
            movie_id, stage, snapshot_date, source, sentiment_score, volume,
            avg_engagement_score, raw_sample_ids
        )
        VALUES (%s, %s, now(), %s, %s, %s, %s, %s)
        ON CONFLICT (movie_id, stage, source) DO UPDATE SET
            snapshot_date = now(),
            sentiment_score = EXCLUDED.sentiment_score,
            volume = EXCLUDED.volume,
            avg_engagement_score = EXCLUDED.avg_engagement_score,
            raw_sample_ids = EXCLUDED.raw_sample_ids
        """,
        (movie_id, stage, source, sentiment_score, volume, avg_engagement_score, raw_sample_ids),
    )
