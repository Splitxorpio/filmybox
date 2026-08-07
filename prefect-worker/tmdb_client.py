import os
import time

import httpx

from rate_limiter import RateLimiter

TMDB_BASE_URL = "https://api.themoviedb.org/3"

# TMDb's documented ceiling is ~40 req/sec; stay well under it to be a
# respectful, cache-friendly client rather than chase the limit.
_limiter = RateLimiter(max_per_second=20)


class TMDbClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ["TMDB_API_KEY"]
        self._client = httpx.Client(
            base_url=TMDB_BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=15.0,
        )

    def _get(self, path: str, params: dict | None = None) -> dict:
        _limiter.wait()
        resp = self._client.get(path, params=params)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 1))
            time.sleep(retry_after)
            return self._get(path, params)
        resp.raise_for_status()
        return resp.json()

    def discover_movie_ids(
        self,
        start_date: str,
        end_date: str,
        min_vote_count: int = 50,
        max_pages: int = 500,
        sort_by: str = "primary_release_date.asc",
    ):
        """Yields TMDb movie ids for wide theatrical releases in a date range.

        with_release_type=3 restricts to Theatrical (excludes limited/festival
        releases per the v1 backfill scope); vote_count.gte filters out
        obscure/straight-to-video noise. sort_by defaults to release-date
        ascending (historical backfill order); pass "popularity.desc" with
        min_vote_count=0 to pull notable *upcoming* movies instead, since
        unreleased titles have near-zero vote counts.
        """
        page = 1
        while page <= max_pages:
            data = self._get(
                "/discover/movie",
                params={
                    "primary_release_date.gte": start_date,
                    "primary_release_date.lte": end_date,
                    "with_release_type": 3,
                    "vote_count.gte": min_vote_count,
                    "sort_by": sort_by,
                    "page": page,
                },
            )
            results = data.get("results", [])
            if not results:
                return
            for movie in results:
                yield movie["id"]
            if page >= data.get("total_pages", 1):
                return
            page += 1

    def get_movie_detail(self, tmdb_id: int) -> dict:
        """One call: details + credits + release_dates (for MPAA cert)."""
        return self._get(
            f"/movie/{tmdb_id}",
            params={"append_to_response": "credits,release_dates"},
        )

    def get_person_detail(self, tmdb_id: int) -> dict:
        return self._get(f"/person/{tmdb_id}")
