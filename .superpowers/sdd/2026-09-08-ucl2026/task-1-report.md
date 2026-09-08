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

## Review fixes (round 1/5)

### RED

Added these regression tests to `test_competition_core.py` before the fixes:

- `test_wc_state_lookup_prefers_scoped_document_and_falls_back_to_legacy`
- `test_prediction_ko_policy_ignores_ucl_client_flag_but_keeps_wc_legacy_fallback`
- `test_require_competition_exposes_unknown_ids_as_http_400`
- uppercase rejection in `test_missing_competition_defaults_to_world_cup_and_unknown_is_rejected`

Command:

```text
.venv/bin/python -m pytest test_competition_core.py -q
```

Expected RED output:

```text
ImportError while importing test module 'test_competition_core.py'
ImportError: cannot import name 'effective_is_ko' from 'src.routes.predict'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
```

### GREEN

Command:

```text
.venv/bin/python -m pytest test_competition_core.py -q
```

Output:

```text
11 passed in 0.62s
```

Full verification command:

```text
.venv/bin/python -m compileall -q src test_competition_core.py && .venv/bin/python -m pytest -q && git diff --check
```

Output:

```text
64 passed in 2.91s
```

### Fixes

- API startup restoration now uses `find_competition_document` for `elo_ratings`, `elo_history`, and `processed_match_ids`, preferring `wc2026:` state IDs and falling back to legacy IDs.
- Competition parsing no longer lowercases or silently trims nonblank IDs; uppercase/mixed IDs are rejected while omitted/blank values still default to WC.
- Prediction KO handling is centralized in `effective_is_ko`: WC retains the legacy client `is_ko` fallback, while UCL ignores that client flag and only accepts explicit stored `extra_time_eligible` metadata.

### Fix self-review

- The startup test exercises the real scoped-first/fallback helper used by `src/api.py`; it proves both the new and legacy paths.
- The KO test covers both UCL client-flag rejection and stored metadata acceptance, plus WC compatibility.
- `require_competition` is directly tested for HTTP 400.
- No provider calls, data files, frontend artifacts, or original-checkout files were touched.
- Full suite and whitespace checks are clean.

### Remaining concerns

- Full stage/leg/extra-time context derivation remains Task 3’s central prediction-service responsibility; this fix prevents the legacy client flag from bypassing that boundary for UCL.
