"""Wikipedia infobox budget lookup - the third budget source this session,
after Wikidata's structured P2130 claim (sparse) and a reverted Bluesky
social-consensus attempt (unreliable for common-word titles).

Correct-by-construction: resolves each movie's exact Wikipedia article via
Wikidata's sitelink relationship (same imdb-id-keyed VALUES batching
wikidata_client.py already uses), eliminating the "wrong topic entirely"
failure mode that broke the Bluesky attempt (a common title like "Run" or
"Border" matching unrelated content). Then parses the infobox's own Budget
field directly - no consensus/corroboration needed, since a Wikipedia
infobox is a single citation-backed field, not scattered social chatter.

USD-only, same scope decision as wikidata_client.py: budgets recorded in a
different currency are skipped, not converted.
"""

import re

import httpx
from bs4 import BeautifulSoup

from rate_limiter import RateLimiter

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

# Same courtesy requirement Wikidata's own SPARQL endpoint already required
# this session (hit a 403 "set a user-agent" wall during research);
# Wikipedia's read API has the same expectation.
_HEADERS = {
    "User-Agent": "FilmyBox/0.1 (box-office prediction side project; budget backfill)",
}

_sitelink_limiter = RateLimiter(max_per_second=1)
_article_limiter = RateLimiter(max_per_second=0.5)

_MONEY_RE = re.compile(
    # Infobox budgets are often a range ("$190-250 million", "$190-$250
    # million", using a hyphen or en-dash) with the unit stated once at the
    # end - the second bound's own "$"/unit is optional in the source text.
    r"\$\s?([\d,]+(?:\.\d+)?)(?:\s?[-–]\s?\$?\s?([\d,]+(?:\.\d+)?))?\s?(million|billion|m|bn)?\b",
    re.IGNORECASE,
)


class WikipediaRateLimited(Exception):
    """Wikipedia/Wikidata is rate-limiting us - stop the run rather than
    burn through the remaining batch against the same wall.
    """


def get_sitelinks(imdb_ids: list[str]) -> dict[str, str]:
    """Batched lookup: (P345 imdb id) -> English Wikipedia article title,
    via each item's enwiki sitelink. Missing ids (no Wikidata item, or no
    English Wikipedia article) are simply absent from the returned dict.
    """
    values = " ".join(f'"{imdb_id}"' for imdb_id in imdb_ids)
    query = f"""
    SELECT ?imdb ?article WHERE {{
      VALUES ?imdb {{ {values} }}
      ?item wdt:P345 ?imdb.
      ?article schema:about ?item;
               schema:isPartOf <https://en.wikipedia.org/>.
    }}
    """
    _sitelink_limiter.wait()
    resp = httpx.get(
        WIKIDATA_SPARQL_URL,
        params={"query": query, "format": "json"},
        headers={**_HEADERS, "Accept": "application/sparql-results+json"},
        timeout=30.0,
    )
    if resp.status_code == 429:
        raise WikipediaRateLimited(resp.text)
    resp.raise_for_status()
    data = resp.json()

    sitelinks: dict[str, str] = {}
    for binding in data["results"]["bindings"]:
        imdb_id = binding["imdb"]["value"]
        article_url = binding["article"]["value"]
        title = article_url.rsplit("/", 1)[-1]
        sitelinks[imdb_id] = title
    return sitelinks


def _parse_money(text: str) -> int | None:
    match = _MONEY_RE.search(text)
    if not match:
        return None
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", "")) if match.group(2) else low
    amount = (low + high) / 2  # range midpoint, e.g. "$190-250 million" -> $220M
    unit = (match.group(3) or "").lower()
    if unit in ("billion", "bn"):
        return int(amount * 1_000_000_000)
    if unit in ("million", "m"):
        return int(amount * 1_000_000)
    # A bare "$X" with no million/billion qualifier and no thousands-comma
    # grouping is almost never a real production budget (too small) - only
    # trust it when the raw number already looks like a full dollar figure.
    return int(amount) if amount >= 100_000 else None


def fetch_infobox_budget(article_title: str) -> int | None:
    """Fetches the article's parsed HTML (via the MediaWiki action API,
    which the article's own infobox is embedded in) and extracts the
    "Budget" row's dollar figure. Returns None if the article has no
    infobox, no Budget row, or the value isn't in USD.
    """
    _article_limiter.wait()
    resp = httpx.get(
        WIKIPEDIA_API_URL,
        params={
            "action": "parse",
            "page": article_title,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
        },
        headers=_HEADERS,
        timeout=15.0,
    )
    if resp.status_code == 429:
        raise WikipediaRateLimited(resp.text)
    resp.raise_for_status()
    data = resp.json()

    html = data.get("parse", {}).get("text")
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    infobox = soup.find("table", class_=re.compile(r"\binfobox\b"))
    if not infobox:
        return None

    for row in infobox.find_all("tr"):
        header = row.find("th")
        if not header or "budget" not in header.get_text(strip=True).lower():
            continue
        value_cell = row.find("td")
        if not value_cell:
            return None
        text = value_cell.get_text(" ", strip=True)
        if "$" not in text:
            # Non-USD (e.g. "€8 million") - skip per the USD-only scope
            # decision, don't guess a conversion.
            return None
        return _parse_money(text)

    return None
