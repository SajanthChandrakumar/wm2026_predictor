import logging
from pymongo.collection import Collection

logger = logging.getLogger(__name__)


def load_archive_from_db(archive_collection: Collection) -> dict:
    """Load the full prediction archive from MongoDB as a {match_id: entry} dict."""
    result = {}
    try:
        for doc in archive_collection.find():
            mid = doc["_id"]
            result[mid] = {k: v for k, v in doc.items() if k != "_id"}
    except Exception as e:
        logger.error(f"Failed to load archive from MongoDB: {e}")
    return result


def upsert_archive_entry(archive_collection: Collection, match_id: str, entry: dict) -> None:
    """Upsert a single archive entry into MongoDB."""
    archive_collection.replace_one(
        {"_id": match_id},
        {"_id": match_id, **entry},
        upsert=True
    )
