import httpx

from rate_limiter import RateLimiter

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USD_UNIT = "http://www.wikidata.org/entity/Q4917"

# Wikidata's public SPARQL endpoint has no hard daily cap like OMDb, but its
# usage policy asks callers to be courteous and identify themselves - stay
# well under any informal limit rather than push it.
_limiter = RateLimiter(max_per_second=1)

_HEADERS = {
    "User-Agent": "FilmyBox/0.1 (box-office prediction side project; budget backfill)",
    "Accept": "application/sparql-results+json",
}


class WikidataRateLimited(Exception):
    """Wikidata's SPARQL endpoint is rate-limiting us (e.g. its own outage-
    triggered aggressive throttling) - stop the run rather than burn
    through every remaining batch against the same wall.
    """


def fetch_budgets(imdb_ids: list[str]) -> dict[str, int]:
    """Batched lookup: (P345 imdb id) -> (P2130 cost, USD only).

    Missing ids (no Wikidata item, or a budget recorded in a non-USD
    currency) are simply absent from the returned dict - same "not found"
    shape as omdb_client.fetch_critic_scores returning None.
    """
    values = " ".join(f'"{imdb_id}"' for imdb_id in imdb_ids)
    query = f"""
    SELECT ?imdb ?budget WHERE {{
      VALUES ?imdb {{ {values} }}
      ?item wdt:P345 ?imdb.
      ?item p:P2130 ?stmt.
      ?stmt psv:P2130 ?bv.
      ?bv wikibase:quantityAmount ?budget.
      ?bv wikibase:quantityUnit <{USD_UNIT}>.
    }}
    """
    _limiter.wait()
    resp = httpx.get(
        WIKIDATA_SPARQL_URL, params={"query": query, "format": "json"}, headers=_HEADERS, timeout=30.0
    )
    if resp.status_code == 429:
        raise WikidataRateLimited(resp.text)
    resp.raise_for_status()
    data = resp.json()

    budgets: dict[str, int] = {}
    for binding in data["results"]["bindings"]:
        imdb_id = binding["imdb"]["value"]
        budget = int(float(binding["budget"]["value"]))
        budgets[imdb_id] = budget
    return budgets
