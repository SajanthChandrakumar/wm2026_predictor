"""
One-shot cleanup: ESPN sync created skeleton entries (numeric IDs, no
pre_match_snapshot) for matches that already existed in the archive under
the legacy hex Odds-API IDs (with empty commence_time, so the date lookup
missed them). Backfill commence_time on the rich originals and delete the
thin ESPN dupes.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

from src.constants import TEAM_MAPPING

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
archive = client["wm2026_db"]["archive"]


def canon(name):
    return TEAM_MAPPING.get(name, name)


groups = defaultdict(list)
for doc in archive.find():
    meta = doc.get("metadata") or {}
    h, a = meta.get("home_team"), meta.get("away_team")
    if h and a:
        # Group by canonical names so "Turkey" and "Türkiye" merge.
        groups[(canon(h), canon(a))].append(doc)

deleted = 0
backfilled = 0
for (h, a), docs in groups.items():
    if len(docs) < 2:
        continue
    # The "rich" entry is the one with a pre_match_snapshot. The other is the
    # ESPN-created skeleton. (If neither has it, keep the older hex-id one.)
    rich = next((d for d in docs if d.get("pre_match_snapshot")), None)
    thin = next((d for d in docs if d is not rich), None)
    if not rich:
        # Both are skeletons — keep the one that has a commence_time set.
        with_ct = [d for d in docs if (d.get("metadata") or {}).get("commence_time")]
        without_ct = [d for d in docs if not (d.get("metadata") or {}).get("commence_time")]
        if with_ct and without_ct:
            rich = with_ct[0]
            thin = without_ct[0]
        else:
            print(f"SKIP {h} vs {a}: ambiguous ({[d['_id'] for d in docs]})")
            continue

    thin_meta = thin.get("metadata") or {}
    thin_ct = thin_meta.get("commence_time")
    if thin_ct and not (rich.get("metadata") or {}).get("commence_time"):
        archive.update_one({"_id": rich["_id"]}, {"$set": {"metadata.commence_time": thin_ct}})
        backfilled += 1

    # Rename the kept entry's teams to canonical so the next ESPN sync's
    # (h, a, date) lookup hits it cleanly instead of creating yet another dupe.
    rich_meta = rich.get("metadata") or {}
    updates = {}
    if rich_meta.get("home_team") != h:
        updates["metadata.home_team"] = h
    if rich_meta.get("away_team") != a:
        updates["metadata.away_team"] = a
    if updates:
        archive.update_one({"_id": rich["_id"]}, {"$set": updates})

    archive.delete_one({"_id": thin["_id"]})
    deleted += 1
    print(f"  merged {h} vs {a}: kept {rich['_id']} (ct={thin_ct}), deleted {thin['_id']}")

print(f"\nDone: deleted {deleted} dupes, backfilled commence_time on {backfilled} entries")
