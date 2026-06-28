import logging

logger = logging.getLogger(__name__)

_LEARNING_BOTS_CODE_VERSION = 2


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
