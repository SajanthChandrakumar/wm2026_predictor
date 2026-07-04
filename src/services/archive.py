import logging

from src.constants import TEAM_MAPPING

logger = logging.getLogger(__name__)

_LEARNING_BOTS_CODE_VERSION = 2


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


def load_archive_from_db(archive_collection) -> dict:
    result = {}
    try:
        for doc in archive_collection.find():
            mid = doc["_id"]
            result[mid] = {k: v for k, v in doc.items() if k != "_id"}
    except Exception as e:
        logger.error(f"Failed to load archive from MongoDB: {e}")
    return result


def upsert_archive_entry(archive_collection, match_id: str, entry: dict) -> None:
    archive_collection.replace_one(
        {"_id": match_id},
        {"_id": match_id, **entry},
        upsert=True
    )


def archive_signature(archive: dict) -> str:
    completed_ids = sorted(
        mid for mid, m in archive.items()
        if (m.get("post_match_result") or {}).get("status") == "completed"
    )
    return f"v{_LEARNING_BOTS_CODE_VERSION}:{len(completed_ids)}:{hash(tuple(completed_ids))}"
