"""Small, credit-free UCL provider adapters.

The adapters return data plus provenance.  They intentionally do not invent a
rating for a club which ClubElo did not publish.
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from datetime import datetime, timezone

import requests

from src.competitions import competition_document_id, find_competition_document, get_competition


CLUBELO_URL = os.getenv("CLUBELO_URL", "https://clubelo.com/Ranking")

# Keep aliases at the provider boundary; callers use the names from their
# fixture/provider payloads and never have to guess which spelling is canonical.
CLUBELO_ALIASES = {
    "Bayern Munich": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "Paris Saint-Germain": "Paris Saint-Germain",
    "Paris SG": "Paris Saint-Germain",
    "Inter Milan": "Inter",
    "Internazionale": "Inter",
    "Atlético Madrid": "Atletico Madrid",
}


class _RankingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _canonical_club(name: str) -> str:
    clean = " ".join((name or "").split())
    return CLUBELO_ALIASES.get(clean, clean)


def parse_clubelo_html(html: str) -> list[dict]:
    """Parse the ranking table into ``team``/``elo`` rows."""
    parser = _RankingParser()
    parser.feed(html or "")
    rows = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        try:
            # Ranking is currently [rank, club, elo].  Looking at the last
            # numeric cell also tolerates an extra coefficient column.
            rank = int(float(cells[0].replace(",", "")))
            elo_index = next(i for i in range(len(cells) - 1, 0, -1) if _is_number(cells[i]))
            elo = float(cells[elo_index].replace(",", ""))
        except (ValueError, StopIteration):
            continue
        team = _canonical_club(cells[1])
        if team:
            rows.append({"rank": rank, "team": team, "team_name": team, "elo": elo, "elo_rating": elo})
    return rows


def _is_number(value: str) -> bool:
    try:
        float(value.replace(",", ""))
        return True
    except (ValueError, AttributeError):
        return False


def ingest_clubelo(
    cache_collection,
    competition=None,
    *,
    observed_at: datetime | None = None,
    request_get=None,
    url: str | None = None,
) -> dict:
    """Fetch ClubElo and persist its cache document with provenance.

    A failed refresh returns the previous rows as ``stale`` when available;
    otherwise it returns ``failed`` with no fabricated ratings.
    """
    comp = get_competition(competition)
    key = "clubelo_ratings"
    cache_id = competition_document_id(comp, key)
    previous = find_competition_document(cache_collection, comp, key) or find_competition_document(
        cache_collection, comp, "elo_ratings"
    ) or {}
    observed = (observed_at or datetime.now(timezone.utc)).isoformat()
    source_url = url or CLUBELO_URL
    getter = request_get or requests.get
    try:
        response = getter(source_url, timeout=10, headers=_conditional_headers(previous))
        response.raise_for_status()
        if getattr(response, "status_code", None) == 304 and previous.get("rows"):
            document = dict(previous)
            document.update({"status": "fresh", "observed_at": observed, "error": None})
            return document
        rows = parse_clubelo_html(getattr(response, "text", ""))
        if not rows:
            raise ValueError("ClubElo ranking page contained no ratings")
        document = {
            "_id": cache_id,
            "competition": comp.id,
            "status": "fresh",
            "source": "clubelo",
            "observed_at": observed,
            "rows": rows,
            "provenance": {
                "source": "clubelo",
                "url": source_url,
                "observed_at": observed,
                "etag": _header(response, "etag"),
                "last_modified": _header(response, "last-modified"),
            },
            "etag": _header(response, "etag"),
        }
        cache_collection.update_one({"_id": cache_id}, {"$set": document}, upsert=True)
        # Keep the existing read-only Elo endpoint compatible while retaining
        # the provider-specific document as the provenance contract.
        cache_collection.update_one(
            {"_id": competition_document_id(comp, "elo_ratings")},
            {"$set": {
                "_id": competition_document_id(comp, "elo_ratings"),
                "competition": comp.id,
                "status": document["status"],
                "source": document["source"],
                "observed_at": document["observed_at"],
                "rows": rows,
                "provenance": document["provenance"],
            }},
            upsert=True,
        )
        return document
    except Exception as exc:
        if previous.get("rows"):
            document = dict(previous)
            document.update({"status": "stale", "error": str(exc), "observed_at": observed})
            return document
        return {
            "_id": cache_id,
            "competition": comp.id,
            "status": "failed",
            "source": "clubelo",
            "observed_at": observed,
            "rows": [],
            "error": str(exc),
            "provenance": {"source": "clubelo", "url": source_url, "observed_at": observed},
        }


def _conditional_headers(previous: dict) -> dict:
    headers = {}
    if previous.get("etag"):
        headers["If-None-Match"] = previous["etag"]
    last_modified = (previous.get("provenance") or {}).get("last_modified")
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _header(response, name: str):
    headers = getattr(response, "headers", {}) or {}
    return headers.get(name) or headers.get(name.title())


def compose_match_sources(
    odds: dict | None,
    elo: dict | None,
    *,
    observed_at: str | None = None,
    odds_status: str = "fresh",
    elo_status: str = "fresh",
    errors: dict | None = None,
) -> dict:
    """Combine source payloads without filling missing data with defaults."""
    has_odds = bool(odds)
    has_elo = bool(elo)
    if has_odds and has_elo:
        mode = "odds+elo"
    elif has_odds:
        mode = "odds-only"
    elif has_elo:
        mode = "elo-only"
    else:
        mode = "unavailable"
    if mode == "unavailable":
        status = "unavailable"
    elif "failed" in (odds_status, elo_status):
        status = "failed" if not (has_odds or has_elo) else "stale"
    elif "stale" in (odds_status, elo_status):
        status = "stale"
    else:
        status = "fresh"
    source_names = [name for present, name in ((has_odds, "odds_api"), (has_elo, "clubelo")) if present]
    result = {
        "status": status,
        "source_mode": mode,
        "source": "+".join(source_names) or "none",
        "odds": odds,
        "elo": elo,
        "observed_at": observed_at,
        "provenance": {
            "odds": {"source": "odds_api", "status": odds_status, "observed_at": observed_at},
            "elo": {"source": "clubelo", "status": elo_status, "observed_at": observed_at},
        },
    }
    if errors:
        result["errors"] = errors
    return result


# Names used by small integrations/readers can stay descriptive and stable.
fetch_clubelo = ingest_clubelo
normalize_sources = compose_match_sources
