"""Copy/tag legacy Mongo documents as World Cup documents.

Run once with the normal application environment. The source collections are
never dropped; IDs and nested user tips are retained.
"""

import os

import certifi
from pymongo import MongoClient

from src.services.migration import migrate_wc_legacy


def main() -> None:
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise SystemExit("MONGO_URI is required")
    db = MongoClient(uri, tlsCAFile=certifi.where())["wm2026_db"]
    result = migrate_wc_legacy(db["archive"], db["cache"], db["custom_bot"])
    print(result)


if __name__ == "__main__":
    main()
