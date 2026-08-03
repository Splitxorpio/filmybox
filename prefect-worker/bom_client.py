import re
import time

import httpx
from bs4 import BeautifulSoup

from rate_limiter import RateLimiter

BOM_BASE_URL = "https://www.boxofficemojo.com"

# No official API here (scraping, per the planning doc's flagged risk) — stay
# conservative and polite rather than push toward whatever undocumented
# threshold triggers bot detection.
_limiter = RateLimiter(max_per_second=1)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

_RELEASE_ID_RE = re.compile(r"(/release/rl\d+)/")


class MovieNotFoundOnBOM(Exception):
    pass


def _parse_money(text: str) -> int | None:
    text = text.strip()
    if not text or text in ("-", "n/a", "N/A"):
        return None
    return int(text.replace("$", "").replace(",", ""))


def _parse_int(text: str) -> int | None:
    text = text.strip()
    if not text or text == "-":
        return None
    return int(text.replace(",", ""))


class BOMClient:
    def __init__(self):
        self._client = httpx.Client(base_url=BOM_BASE_URL, headers=_HEADERS, timeout=20.0, follow_redirects=True)

    def _get(self, path: str) -> str:
        _limiter.wait()
        resp = self._client.get(path)
        if resp.status_code == 404:
            raise MovieNotFoundOnBOM(path)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            return self._get(path)
        resp.raise_for_status()
        return resp.text

    def get_box_office(self, imdb_id: str) -> dict:
        """Returns {"domestic": int|None, "international": int|None,
        "worldwide": int|None, "weekly": [{"weekend_number", "weekend_gross",
        "theater_count"}, ...]}. Raises MovieNotFoundOnBOM if BOM has no page
        for this imdb_id.
        """
        title_html = self._get(f"/title/{imdb_id}/")
        totals, domestic_release_path = self._parse_title_page(title_html)

        weekly: list[dict] = []
        if domestic_release_path:
            weekend_html = self._get(f"{domestic_release_path}/weekend/")
            weekly = self._parse_weekend_page(weekend_html)

        return {**totals, "weekly": weekly}

    @staticmethod
    def _parse_title_page(html: str) -> tuple[dict, str | None]:
        soup = BeautifulSoup(html, "lxml")
        totals = {"domestic": None, "international": None, "worldwide": None}

        summary = soup.find(class_="mojo-performance-summary-table")
        if summary:
            for block in summary.find_all(class_="a-section", recursive=False):
                label_span = block.find(class_="a-size-small")
                money_span = block.find(class_="money")
                if not label_span or not money_span:
                    continue
                label = label_span.get_text(strip=True).lower()
                value = _parse_money(money_span.get_text())
                if "domestic" in label:
                    totals["domestic"] = value
                elif "international" in label:
                    totals["international"] = value
                elif "worldwide" in label:
                    totals["worldwide"] = value

        domestic_release_path = None
        for link in soup.find_all("a"):
            if link.get_text(strip=True) != "Domestic":
                continue
            match = _RELEASE_ID_RE.search(link.get("href", ""))
            if match:
                domestic_release_path = match.group(1)
                break

        return totals, domestic_release_path

    @staticmethod
    def _parse_weekend_page(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find(class_="mojo-body-table")
        if not table:
            return []

        header_cells = table.find("tr").find_all("th")
        column_names = []
        for th in header_cells:
            title_el = th.find(attrs={"title": True})
            column_names.append(title_el["title"] if title_el else None)

        rows = []
        seen_weekend_numbers: set[int] = set()
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) != len(column_names):
                continue
            by_name = dict(zip(column_names, cells))

            gross_cell = by_name.get("Weekend Gross")
            theaters_cell = by_name.get("Number of Theaters")
            week_cell = by_name.get("Weekend")
            if gross_cell is None or theaters_cell is None or week_cell is None:
                continue

            weekend_number = _parse_int(week_cell.get_text())
            if weekend_number is None:
                continue
            if weekend_number in seen_weekend_numbers:
                # Holiday frames (e.g. MLK/Thanksgiving) get a second row for
                # the same week - an extended-weekend total. Keep the first
                # (standard 3-day) figure so weekends stay comparable across
                # movies that didn't open on a holiday.
                continue
            seen_weekend_numbers.add(weekend_number)

            rows.append(
                {
                    "weekend_number": weekend_number,
                    "weekend_gross": _parse_money(gross_cell.get_text()),
                    "theater_count": _parse_int(theaters_cell.get_text()),
                }
            )
        return rows
