"""Copy-first migration helpers for legacy World Cup Mongo documents."""

from __future__ import annotations

from copy import deepcopy


WC_COMPETITION = "wc2026"
SCHEMA_VERSION = 1


def _documents(collection):
    try:
        return list(collection.find())
    except TypeError:
        return list(collection.find({}))


def _tagged(document: dict) -> dict:
    copy = deepcopy(document)
    copy.setdefault("competition", WC_COMPETITION)
    copy.setdefault("schema_version", SCHEMA_VERSION)
    return copy


def _copy_collection(source, destination) -> int:
    copied = 0
    for document in _documents(source):
        if not isinstance(document, dict) or "_id" not in document:
            continue
        if document.get("competition") not in (None, WC_COMPETITION):
            continue
        tagged = _tagged(document)
        current = destination.find_one({"_id": tagged["_id"]})
        if current == tagged:
            continue
        if hasattr(destination, "replace_one"):
            destination.replace_one({"_id": tagged["_id"]}, tagged, upsert=True)
        else:
            destination.update_one(
                {"_id": tagged["_id"]},
                {"$set": {key: value for key, value in tagged.items() if key != "_id"}, "$setOnInsert": {"_id": tagged["_id"]}},
                upsert=True,
            )
        copied += 1
    return copied


def migrate_wc_legacy(
    archive_collection,
    cache_collection,
    custom_bot_collection,
    *,
    wc_archive_collection=None,
    wc_cache_collection=None,
    wc_custom_bot_collection=None,
    schema_version: int = SCHEMA_VERSION,
) -> dict:
    """Tag/copy legacy documents as WC data without deleting the source.

    Destinations may be separate collections during a rollout or the legacy
    collections in-place for the existing WC compatibility names. IDs are
    retained exactly, making archive match IDs and user tips stable.
    """
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported migration schema version: {schema_version}")
    copied = 0
    copied += _copy_collection(archive_collection, wc_archive_collection or archive_collection)
    copied += _copy_collection(cache_collection, wc_cache_collection or cache_collection)
    copied += _copy_collection(custom_bot_collection, wc_custom_bot_collection or custom_bot_collection)
    return {
        "status": "fresh",
        "source": "legacy_migration",
        "competition": WC_COMPETITION,
        "schema_version": SCHEMA_VERSION,
        "copied": copied,
    }


# Descriptive alias for scripts and small integrations.
migrate_legacy_to_wc = migrate_wc_legacy
