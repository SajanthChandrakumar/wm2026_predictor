# Task 1 Report: Competition core and storage isolation

## Result

Implemented the competition registry and competition-scoped storage contract on `codex/ucl2026`.

## RED

Command:

```text
.venv/bin/python -m pytest test_competition_core.py -q
```

Output before production implementation:

```text
ImportError while importing test module 'test_competition_core.py'
ModuleNotFoundError: No module named 'src.competitions'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

The failure was caused by the intentionally missing competition module.

## GREEN

Focused command:

```text
.venv/bin/python -m pytest test_competition_core.py -q
```

Output:

```text
8 passed in 0.64s
```

Full verification command:

```text
.venv/bin/python -m compileall -q src test_competition_core.py && .venv/bin/python -m pytest -q && git diff --check
```

Output:

```text
61 passed in 2.87s
```

## Files changed

- `src/competitions.py` — registry, parser/defaulting, public metadata, collection selection, scoped document IDs, and WC legacy reads.
- `src/api.py` — competition collection maps, `GET /api/competitions`, and optional competition handling for archive, state, tip, quota, maintenance-style, and Elo routes.
- `src/routes/matches.py` — competition-aware cache/archive selection and namespaced match cache writes.
- `src/routes/predict.py` — competition-aware totals/match cache access.
- `src/routes/custom_bot.py` — competition-scoped archive and custom-bot state with WC legacy reads.
- `src/routes/simulate.py` — competition-scoped simulation cache.
- `src/services/archive.py` — RAM archive cache keyed by Mongo collection.
- `src/services/odds_helpers.py` — optional competition-scoped totals cache.
- `src/services/elo_sync.py` — competition-scoped cache/state document IDs with WC legacy reads.
- `test_competition_core.py` — focused registry, defaulting, route, archive-cache, and custom-bot isolation tests.

## Self-review

- Supported IDs are exactly `wc2026` and `ucl2026`; omitted or blank values resolve to `wc2026`.
- Invalid route IDs are rejected with HTTP 400 before provider or storage work.
- WC responses retain existing response fields; WC storage reads fall back to unscoped legacy IDs while new writes use scoped IDs.
- UCL uses separate archive/cache/custom-bot Mongo collections and scoped document IDs.
- Archive RAM snapshots are keyed by collection name/identity, preventing cross-competition reuse.
- No live provider calls are used by the tests.
- `data/elo_history.json`, `data/elo_ratings.csv`, `frontend-v2/dist`, and the original checkout were not touched.
- `git diff --check` is clean.

## Concerns / follow-up boundaries

- Provider-specific ESPN fetching and UCL odds/Elo ingestion remain intentionally deferred to Task 2; this task only establishes the shared registry and storage boundary.
- Existing local Elo/scores files remain governed by the current WC sync implementation; later UCL provider/state work should give those local artifacts competition-specific paths before enabling UCL maintenance.
