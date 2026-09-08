# Task 2 Report: UCL providers, snapshots, and protected maintenance

## Result

Implemented the Task 2 provider and maintenance boundary on `codex/ucl2026`.
The implementation keeps provider calls out of public forced refreshes, stores
truthful source/bucket states, and preserves existing WC adapter entry points.

## RED evidence

Focused command before implementation:

```text
.venv/bin/python -m pytest test_task2_providers.py -q
```

Expected RED output:

```text
ImportError while importing test module 'test_task2_providers.py'
ModuleNotFoundError: No module named 'src.routes.maintenance'
```

The focused tests were written first against the missing provider, snapshot,
maintenance, and route interfaces. No live provider call was used.

## GREEN evidence

Focused command:

```text
.venv/bin/python -m pytest test_task2_providers.py -q
```

Output:

```text
13 passed in 0.66s
```

Full Python suite:

```text
.venv/bin/python -m pytest -q
```

Output:

```text
77 passed in 2.89s
```

Additional verification:

```text
.venv/bin/python -m compileall -q src test_task2_providers.py
git diff --check
```

Both completed successfully.

## Files changed

- `src/services/espn_data.py` — configurable ESPN endpoint/slug resolution,
  bounded UCL date windows, event-ID deduplication, and competition-aware
  completed scores/standings.
- `src/odds_engine.py` — configurable per-competition Odds API sport keys,
  one bulk `h2h,totals` adapter, and WC-compatible wrappers.
- `src/odds_engine_apifootball.py` — competition-aware bulk adapter for the
  existing optional API-Football implementation.
- `src/services/ucl_providers.py` — ClubElo HTML ingestion, alias mapping,
  cache/ETag contract, provenance, explicit source modes, and truthful status
  values without rating fallbacks.
- `src/services/snapshots.py` — exact `t24h=1440`, `t6h=360`, `t75m=75`,
  `t30m=30`, `t15m=15` bucket offsets; append-only snapshots; bucket state;
  and latest eligible T-15 selection.
- `src/services/maintenance.py` — unique Mongo lease claim, stale-lease
  takeover, due-bucket detection, missed-bucket marking, one bulk provider
  call per competition/run, idempotency, and failure/unavailable states.
- `src/routes/maintenance.py` — `POST /api/internal/maintenance` with
  constant-time Bearer `CRON_SECRET` authorization.
- `src/routes/matches.py` — competition-aware provider calls and cache-only
  public `force=true` behavior.
- `src/services/elo_sync.py` — competition-aware ESPN score/standings calls.
- `src/api.py` — registered the protected maintenance router.
- `test_task2_providers.py` — captured/fake provider tests for all Task 2
  requirements, including auth, leases, idempotency, missed buckets, T-15,
  provider failures, and credit caps.

## Self-review

- ESPN UCL requests are bounded to seven-day windows and deduplicated by event
  ID; WC defaults retain the previous single-window path.
- Odds identifiers resolve from the competition registry with environment
  overrides (`ODDS_API_<COMPETITION>_SPORT_KEY`, ESPN slug/template overrides).
- ClubElo cache entries carry source, URL, ETag/Last-Modified, and observation
  metadata. A failed refresh returns `stale` only when prior rows exist;
  otherwise it returns `failed` with an empty rating set.
- Odds-only, Elo-only, both-source, and unavailable modes are explicit.
- Unknown clubs are never assigned 1500/1650 or any other synthetic rating.
- A late run marks earlier missed buckets without placing a later observation
  into those buckets; only the latest due bucket receives the observation.
- T-15 selection rejects observations after `kickoff - 15 minutes`.
- `force=true` returns before lease/provider/storage work in maintenance and is
  cache-only in the public matches route.
- A live lease blocks a run; an expired lease can be replaced using the old
  lease value. A run with no due bucket makes zero provider calls.
- Existing WC method names and route defaults remain available.
- Protected data files, `frontend-v2/dist`, and the original checkout were not
  modified.

## Concerns

- ClubElo is intentionally an ingestion/cache adapter only; Task 3 owns the
  central prediction service and its use of source modes.
- The optional API-Football adapter uses its configured UCL league ID and the
  provider's existing 2026 season convention; no live API-Football request was
  made in tests.
- The route is registered in `src/api.py`, whose existing application startup
  still requires the repository's normal Mongo/provider environment variables.
