import time
import logging

from src.constants import TEAM_MAPPING

logger = logging.getLogger(__name__)

# ── In-process archive cache ─────────────────────────────────────────────────
# Avoids a full MongoDB collection scan on every /api/matches cache-hit.
# Invalidated explicitly after any write (upsert_archive_entry) so reads
# always see the latest user tips and match results within 2 minutes.
_archive_mem: dict = {}
_archive_mem_ts: float = 0.0
_ARCHIVE_MEM_TTL = 120  # seconds


def _canon_team(name: str) -> str:
    """Canonical team name for cross-source matching (ESPN ↔ Odds API ↔ archive)."""
    return TEAM_MAPPING.get(name, name)


def build_archive_id_index(archive: dict):
    """
    Build a lookup so an external fixture (home, away, date) can be resolved to
    the existing archive _id. Prefer a date-qualified key so a stale entry can't
    absorb a different match with the same pairing; fall back to (home, away)
    for legacy entries written without a commence_time.
    """
    dated = {}
    undated = {}
    for mid, entry in archive.items():
        meta = entry.get("metadata") or {}
        h, a, ct = meta.get("home_team"), meta.get("away_team"), meta.get("commence_time") or ""
        if not (h and a):
            continue
        hc, ac = _canon_team(h), _canon_team(a)
        if ct[:10]:
            dated[(hc, ac, ct[:10])] = mid
        else:
            undated.setdefault((hc, ac), mid)
    return dated, undated


def resolve_archive_id(index, home: str, away: str, date: str):
    """Return the archive _id for a fixture, or None if it's a new match."""
    dated, undated = index
    hc, ac = _canon_team(home), _canon_team(away)
    d = (date or "")[:10]
    return dated.get((hc, ac, d)) or undated.get((hc, ac))


def load_archive_from_db(archive_collection, force: bool = False) -> dict:
    global _archive_mem, _archive_mem_ts
    now = time.time()
    if not force and _archive_mem and (now - _archive_mem_ts) < _ARCHIVE_MEM_TTL:
        return _archive_mem  # serve from RAM — no MongoDB round-trip
    result = {}
    try:
        for doc in archive_collection.find():
            mid = doc["_id"]
            result[mid] = {k: v for k, v in doc.items() if k != "_id"}
        _archive_mem = result
        _archive_mem_ts = now
    except Exception as e:
        logger.error(f"Failed to load archive from MongoDB: {e}")
        if _archive_mem:  # return stale cache on error rather than empty dict
            return _archive_mem
    return result


def invalidate_archive_mem_cache() -> None:
    """Call after any write so the next read fetches fresh data from MongoDB."""
    global _archive_mem_ts
    _archive_mem_ts = 0.0


def upsert_archive_entry(archive_collection, match_id: str, entry: dict) -> None:
    archive_collection.replace_one(
        {"_id": match_id},
        {"_id": match_id, **entry},
        upsert=True
    )
    invalidate_archive_mem_cache()  # next read will re-fetch from MongoDB
