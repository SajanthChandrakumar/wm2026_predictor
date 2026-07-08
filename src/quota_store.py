"""Persist API-quota counters in MongoDB so they survive on Render.

Render's filesystem is ephemeral — it resets on every deploy, restart, and
free-tier spin-down. The quota counters used to live in `data/*.json`, which
meant `/api/quota` returned `--` after every cold start. Everything else in
this app (matches, archive, standings) is persisted in MongoDB;
this module brings quota in line with that.

Falls back to the local filesystem when MONGO_URI is unset (local dev), so the
odds engines keep working without a database.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# provider -> local-dev fallback filename (kept identical to the old behaviour)
_FILES = {
    "odds": "api_quota_odds.json",
    "football": "api_quota.json",
}
_DEFAULT = {"remaining": "--", "used": "?"}

_collection = None
_resolved = False  # whether we've attempted the (lazy, one-shot) Mongo connect


def _get_collection():
    """Lazily connect to the same `wm2026_db.cache` collection api.py uses.

    Returns None when MONGO_URI is unset or the connection fails — callers then
    fall back to the local filesystem. The connection is attempted once and the
    result (collection or None) is cached for the process lifetime.
    """
    global _collection, _resolved
    if _resolved:
        return _collection
    _resolved = True

    uri = os.getenv("MONGO_URI")
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        import certifi
        client = MongoClient(uri, tlsCAFile=certifi.where())
        _collection = client["wm2026_db"]["cache"]
    except Exception as e:
        logger.warning(f"quota_store: MongoDB unavailable, using files: {e}")
        _collection = None
    return _collection


def write_quota(provider: str, data: dict) -> None:
    """Persist the latest quota counters for a provider ('odds' | 'football')."""
    coll = _get_collection()
    if coll is not None:
        try:
            coll.update_one(
                {"_id": f"quota_{provider}"},
                {"$set": {"data": data}},
                upsert=True,
            )
            return
        except Exception as e:
            logger.warning(f"quota_store: Mongo write failed ({provider}): {e}")

    # Filesystem fallback (local dev without MongoDB)
    fname = _FILES.get(provider)
    if not fname:
        return
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(os.path.join(_DATA_DIR, fname), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.warning(f"quota_store: file write failed ({provider}): {e}")


def read_quota(provider: str) -> dict:
    """Return the latest stored quota for a provider, or a placeholder default."""
    coll = _get_collection()
    if coll is not None:
        try:
            doc = coll.find_one({"_id": f"quota_{provider}"})
            if doc and isinstance(doc.get("data"), dict):
                return doc["data"]
        except Exception as e:
            logger.warning(f"quota_store: Mongo read failed ({provider}): {e}")

    fname = _FILES.get(provider)
    if fname:
        try:
            with open(os.path.join(_DATA_DIR, fname), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_DEFAULT)
