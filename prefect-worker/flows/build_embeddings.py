"""Movie embedding pipeline: builds a text descriptor per movie (genres,
director, top cast, studio, budget tier) and embeds it with a sentence-
transformers model, populating movie_embeddings for comp-similarity search.

Run manually (module form, see tmdb_backfill.py's docstring for why):
    docker compose run --rm --no-deps prefect-worker python -m flows.build_embeddings

This is the learned-embedding-space step from the planning doc's Modeling
Approach section, intended to eventually replace/supplement the heuristic
comps in api/app/queries.py:get_comps (shared genre/director/actor scoring).

Deliberately plain Python, not @flow/@task — see tmdb_backfill.py's
docstring for why.
"""

from embedding_client import MODEL_VERSION, embed_texts
from db import get_connection, get_credits_for_movies, get_movies_missing_embeddings, upsert_movie_embedding

BATCH_SIZE = 500


def _budget_tier(budget_usd: int | None) -> str:
    if not budget_usd:
        return "unknown"
    if budget_usd < 10_000_000:
        return "under $10M"
    if budget_usd < 50_000_000:
        return "$10M-$50M"
    if budget_usd < 100_000_000:
        return "$50M-$100M"
    if budget_usd < 200_000_000:
        return "$100M-$200M"
    return "$200M+"


def _build_text(movie: dict, credits: list[dict]) -> str:
    year = movie["release_date"].year if movie["release_date"] else "unknown year"
    genres = ", ".join(movie["genres"]) if movie["genres"] else "unknown"
    directors = ", ".join(c["name"] for c in credits if c["role_type"] == "director") or "unknown"
    top_actors = [c["name"] for c in credits if c["role_type"] == "actor"][:5]
    top_cast = ", ".join(top_actors) if top_actors else "unknown"
    studio = movie["studio_name"] or "unknown studio"
    budget_tier = _budget_tier(movie["budget_usd"])

    # Deliberately excludes movie['title']: title text caused the model to
    # cluster on superficial subword overlap (e.g. "Fast X" nearest to "X" and
    # "Saw X"; "Get Out" nearest to "Inside Out"/"Lights Out") rather than the
    # structured genre/cast/director signal this embedding is meant to carry.
    return (
        f"Released {year}. Genres: {genres}. Directed by {directors}. "
        f"Starring {top_cast}. Studio: {studio}. Budget tier: {budget_tier}."
    )


def build_embeddings_flow():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            movies = get_movies_missing_embeddings(cur)
        print(f"[build-embeddings] {len(movies)} movies need embeddings")

        for batch_start in range(0, len(movies), BATCH_SIZE):
            batch = movies[batch_start : batch_start + BATCH_SIZE]

            with conn.cursor() as cur:
                credits_by_movie = get_credits_for_movies(cur, [m["id"] for m in batch])

            texts = [_build_text(m, credits_by_movie.get(m["id"], [])) for m in batch]
            embeddings = embed_texts(texts)

            with conn.cursor() as cur:
                for movie, embedding in zip(batch, embeddings):
                    upsert_movie_embedding(cur, movie["id"], embedding, MODEL_VERSION)
            conn.commit()

            print(f"[build-embeddings] processed {min(batch_start + BATCH_SIZE, len(movies))}/{len(movies)}")
    finally:
        conn.close()

    print("[build-embeddings] done")


if __name__ == "__main__":
    build_embeddings_flow()
