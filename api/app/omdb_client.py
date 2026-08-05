import httpx

OMDB_BASE_URL = "https://www.omdbapi.com/"


class OMDbRateLimited(Exception):
    """OMDb's free-tier daily cap (1,000 req/day) has been hit."""


def _parse_int(text: str | None) -> int | None:
    if not text or text == "N/A":
        return None
    return int(text.replace(",", "").replace("%", ""))


def _parse_float(text: str | None) -> float | None:
    if not text or text == "N/A":
        return None
    return float(text)


def fetch_critic_scores(imdb_id: str, api_key: str) -> dict | None:
    """Returns {"imdb_rating", "imdb_votes", "rotten_tomatoes_pct",
    "metacritic_score"}, or None if OMDb has no data for this movie.
    Raises OMDbRateLimited if the daily quota is exhausted.
    """
    resp = httpx.get(OMDB_BASE_URL, params={"i": imdb_id, "apikey": api_key}, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    if data.get("Response") == "False":
        if data.get("Error") == "Request limit reached!":
            raise OMDbRateLimited()
        return None

    ratings = {r["Source"]: r["Value"] for r in data.get("Ratings", [])}
    rt_value = ratings.get("Rotten Tomatoes")
    mc_value = ratings.get("Metacritic")

    return {
        "imdb_rating": _parse_float(data.get("imdbRating")),
        "imdb_votes": _parse_int(data.get("imdbVotes")),
        "rotten_tomatoes_pct": _parse_int(rt_value) if rt_value else None,
        "metacritic_score": int(mc_value.split("/")[0]) if mc_value else None,
    }
