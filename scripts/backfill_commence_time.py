"""
One-shot: fill metadata.commence_time on archive entries that lack it, using
the full ESPN scoreboard (played + upcoming). Fixes the Performance view
ordering, which sorts by commence_time and clumps undated entries at the end.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

from src.services import espn_data
from src.services.archive import _canon_team

load_dotenv()
client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
archive = client["wm2026_db"]["archive"]

# (canon_home, canon_away) -> commence_time from every ESPN fixture
name_ct = {}
for f in espn_data.get_scoreboard():
    if f.get("commence_time"):
        name_ct[(_canon_team(f["home_team"]), _canon_team(f["away_team"]))] = f["commence_time"]

print(f"ESPN scoreboard: {len(name_ct)} fixtures with dates")

filled = 0
unmatched = []
for doc in archive.find():
    meta = doc.get("metadata") or {}
    if meta.get("commence_time"):
        continue
    h, a = meta.get("home_team"), meta.get("away_team")
    ct = name_ct.get((_canon_team(h or ""), _canon_team(a or "")))
    if ct:
        archive.update_one({"_id": doc["_id"]}, {"$set": {"metadata.commence_time": ct}})
        filled += 1
        print(f"  filled {h} vs {a} -> {ct}")
    else:
        unmatched.append((doc["_id"], h, a))

print(f"\nDone: filled {filled} entries")
if unmatched:
    print(f"Unmatched ({len(unmatched)}) — no ESPN fixture found:")
    for mid, h, a in unmatched:
        print(f"  {mid}: {h} vs {a}")
