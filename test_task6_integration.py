from datetime import datetime, timedelta, timezone
import os
import importlib
from pathlib import Path
import subprocess
import sys

import pytest

from test_task2_providers import MemoryCollection
from src.competitions import competition_document_id
from src.constants import TEAM_MAPPING
from src.routes.matches import init_router as matches_router
from src.routes.simulate import init_router as simulate_router
from src.services.maintenance import run_maintenance
from src.services.archive import load_archive_from_db
from src.services.migration import migrate_wc_legacy
from src.services.prediction import freeze_prediction
from src.services.elo_sync import perform_elo_sync
from src.services.snapshots import append_odds_snapshot
from src.services.ucl_simulation import simulate_ucl_tournament
from src.math_engine import MathEngine


def _ucl_teams_and_fixtures():
    teams = [f"Team {index:02d}" for index in range(36)]
    fixtures = []
    for round_no in range(4):
        for team_index, home in enumerate(teams):
            away = teams[(team_index + round_no + 1) % len(teams)]
            fixtures.append({
                "id": f"m-{round_no}-{team_index}",
                "home_team": home,
                "away_team": away,
                "status": "completed",
                "score_90": "0:0",
            })
    return teams, fixtures


def test_public_match_cache_miss_is_explicitly_unavailable_without_provider_calls(monkeypatch):
    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise AssertionError("public matches must not call paid providers")

    monkeypatch.setattr(
        "src.routes.matches.espn_data.get_scoreboard",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("public matches must not collect fixtures")),
    )
    endpoint = matches_router(
        object(), Provider(), {"ucl2026": MemoryCollection()}, {"ucl2026": MemoryCollection()}
    ).routes[0].endpoint

    result = endpoint(competition="ucl2026")

    assert result["status"] == "unavailable"
    assert result["source"] == "matches_cache"
    assert result["observed_at"]
    assert result["error"]


def test_force_matches_uses_the_cached_presentation_path(monkeypatch):
    cache = MemoryCollection([{
        "_id": "ucl2026:matches_cache",
        "data": [{"id": "e1", "home_team": "Bayern Munich", "away_team": "Arsenal"}],
    }])
    calls = []

    class Engine:
        team_forms = {}

        def reload_elo_data(self):
            calls.append("reload")

    def present(matches, *args, **kwargs):
        calls.append(matches)
        return [{"id": "e1", "presented": True}]

    monkeypatch.setattr("src.routes.matches._enrich_edge", present)
    endpoint = matches_router(Engine(), object(), {"ucl2026": cache}, {"ucl2026": MemoryCollection()}).routes[0].endpoint

    result = endpoint(force=True, competition="ucl2026")

    assert result == [{"id": "e1", "presented": True}]
    assert calls[0] == "reload"
    assert calls[1][0]["id"] == "e1"


def test_cached_pending_wc_match_uses_full_prediction_contract_without_provider_calls():
    cache = MemoryCollection([{
        "_id": "wc2026:matches_cache",
        "data": [{
            "id": "wc-1",
            "home_team": "France",
            "away_team": "Spain",
            "commence_time": "2026-06-20T18:00:00Z",
            "round": "Group A",
            "completed": False,
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
        }],
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise AssertionError("cached WC reads must not call providers")

    endpoint = matches_router(
        MathEngine("data/elo_ratings.csv"),
        Provider(),
        {"wc2026": cache},
        {"wc2026": MemoryCollection()},
    ).routes[0].endpoint

    result = endpoint(competition="wc2026")
    match = result[0]

    assert match["top_tip"] != "N/A"
    assert match["max_xp"] > 0
    assert match["source"]
    assert match["provenance"]
    assert match["context"]["competition"] == "wc2026"


def test_ucl_standings_api_derives_one_valid_frontend_group_from_schedule(monkeypatch):
    teams, fixtures = _ucl_teams_and_fixtures()
    cache = MemoryCollection([{
        "_id": "ucl2026:matches_cache",
        "data": fixtures,
        "teams": teams,
    }])
    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=50")
    monkeypatch.setenv("ODDS_API_KEY", "test-only-key")
    api = importlib.import_module("src.api")
    monkeypatch.setattr(api, "cache_collections", {"ucl2026": cache})

    groups = api.get_standings(competition="ucl2026")

    assert groups and len(groups) == 1
    assert groups[0]["name"] == "UCL League Phase"
    rows = groups[0]["rows"]
    assert len(rows) == 36
    assert {row["team"] for row in rows} == set(teams)
    assert {row["pos"] for row in rows} == set(range(1, 37))


def test_ucl_standings_api_returns_empty_for_unestablished_schedule(monkeypatch):
    teams, fixtures = _ucl_teams_and_fixtures()
    cache = MemoryCollection([{
        "_id": "ucl2026:matches_cache",
        "data": fixtures[:-1],
        "teams": teams,
    }])
    monkeypatch.setenv("MONGO_URI", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=50")
    monkeypatch.setenv("ODDS_API_KEY", "test-only-key")
    api = importlib.import_module("src.api")
    monkeypatch.setattr(api, "cache_collections", {"ucl2026": cache})

    assert api.get_standings(competition="ucl2026") == []


def test_ucl_simulation_routes_clamp_large_and_negative_runs(monkeypatch):
    cache = MemoryCollection([{
        "_id": "ucl2026:matches_cache",
        "data": [{
            "id": "m1",
            "home_team": "Team 01",
            "away_team": "Team 02",
            "status": "scheduled",
            "matrix": {"0:0": 1.0},
        }],
        "teams": ["Team 01", "Team 02"],
    }])
    observed = []

    def fake_simulation(*args, **kwargs):
        observed.append(kwargs["n_runs"])
        return {"status": "fresh", "n_runs": kwargs["n_runs"]}

    monkeypatch.setattr("src.routes.simulate.simulate_ucl_tournament", fake_simulation)
    router = simulate_router(object(), {"ucl2026": cache})
    ucl_endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_ucl")
    knockout_endpoint = next(route.endpoint for route in router.routes if route.path == "/api/simulate_knockout")

    assert ucl_endpoint(runs=999999, competition="ucl2026")["n_runs"] == 100000
    assert ucl_endpoint(runs=-5, competition="ucl2026")["n_runs"] == 1000
    assert knockout_endpoint(runs=999999, competition="ucl2026")["n_runs"] == 100000
    assert knockout_endpoint(runs=-5, competition="ucl2026")["n_runs"] == 1000
    assert observed == [100000, 1000, 100000, 1000]


def test_migration_script_direct_invocation_bootstraps_repo_imports_and_dotenv():
    repo = Path(__file__).resolve().parent
    env = os.environ.copy()
    env.pop("MONGO_URI", None)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "scripts/migrate_wc_legacy.py"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "MONGO_URI is required" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_public_ui_does_not_expose_protected_elo_sync_control():
    repo = Path(__file__).resolve().parent
    sidebar = (repo / "frontend-v2/src/components/layout/Sidebar.tsx").read_text()
    api = (repo / "frontend-v2/src/lib/api.ts").read_text()
    queries = (repo / "frontend-v2/src/hooks/queries.ts").read_text()

    assert "Sync Elo Ratings" not in sidebar
    assert "useSyncElo" not in sidebar
    assert "syncElo:" not in api
    assert "useSyncElo" not in queries
    assert "Refresh Data" in sidebar


def test_empty_ucl_clubelo_sync_has_truthful_metadata(tmp_path):
    before = datetime.now(timezone.utc)
    result = perform_elo_sync(
        object(),
        object(),
        MemoryCollection(),
        MemoryCollection(),
        str(tmp_path),
        str(tmp_path / "scores.json"),
        object,
        competition="ucl2026",
    )
    observed = datetime.fromisoformat(result["observed_at"])

    assert result["status"] == "unavailable"
    assert result["source"] == "clubelo"
    assert result["error"]
    assert observed >= before


def test_ucl_clubelo_sync_reconstructs_missed_completed_tip(tmp_path):
    class ArchiveCollection(MemoryCollection):
        def replace_one(self, query, document, upsert=False):
            self.documents[query["_id"]] = dict(document)

    cache = MemoryCollection([{
        "_id": "ucl2026:clubelo_ratings",
        "status": "fresh",
        "source": "clubelo",
        "observed_at": "2026-09-08T12:00:00+00:00",
        "rows": [
            {"team_name": "Dortmund", "elo_rating": 1891.0},
            {"team_name": "Villarreal", "elo_rating": 1797.0},
        ],
    }])
    archive = ArchiveCollection([{
        "_id": "ucl-1",
        "metadata": {
            "home_team": "Borussia Dortmund",
            "away_team": "Villarreal",
            "commence_time": "2026-09-08T19:00:00Z",
            "is_ko_phase": False,
        },
        "pre_match_snapshot": None,
        "prediction": {"top_tip": None},
        "post_match_result": {"status": "completed", "actual_score": "3:2"},
    }])

    result = perform_elo_sync(
        MathEngine("data/elo_ratings.csv", TEAM_MAPPING),
        object(),
        cache,
        archive,
        str(tmp_path),
        str(tmp_path / "scores.json"),
        MathEngine,
        competition="ucl2026",
    )
    rebuilt = archive.documents["ucl-1"]

    assert result["updates"] == 1
    assert rebuilt["prediction"]["algo_reconstructed"] is True
    assert rebuilt["prediction"]["source_mode"] == "elo-only"
    assert rebuilt["prediction"]["top_tip"]
    assert rebuilt["post_match_result"]["algo_points"] >= 0


def test_maintenance_refreshes_ucl_fixtures_and_flattens_provider_odds():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=15)
    cache = MemoryCollection()
    fixture_calls = []

    def fetch_fixtures(**kwargs):
        fixture_calls.append(kwargs)
        return [{
            "id": "e1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
            "round": "League Phase",
        }]

    class Provider:
        calls = 0

        def get_competition_odds(self, competition, market):
            self.calls += 1
            return [{
                "id": "e1",
                "home_team": "Bayern Munich",
                "away_team": "Arsenal",
                "bookmakers": [{
                    "key": "book-a",
                    "markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": "Bayern Munich", "price": 2.0},
                            {"name": "Draw", "price": 3.2},
                            {"name": "Arsenal", "price": 4.0},
                        ]},
                        {"key": "totals", "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.9},
                            {"name": "Under", "point": 2.5, "price": 2.0},
                        ]},
                    ],
                }],
            }]

    result = run_maintenance(
        {"ucl2026": cache},
        Provider(),
        competition="ucl2026",
        now=now,
        fixture_fetcher=fetch_fixtures,
        clubelo_ingestor=lambda *args, **kwargs: {"status": "fresh", "source": "clubelo"},
    )

    assert result["status"] == "success"
    assert fixture_calls and fixture_calls[0]["chunk_days"] == 7
    assert fixture_calls[0]["days_back"] == 71
    assert fixture_calls[0]["days_forward"] == 293
    matches = cache.find_one({"_id": competition_document_id("ucl2026", "matches_cache")})["data"]
    assert matches[0]["odds"] == {
        "home": 2.0,
        "draw": 3.2,
        "away": 4.0,
        "over25": 1.9,
        "under25": 2.0,
    }
    snapshots = [doc for doc in cache.inserts if "odds_snapshot" in doc["_id"]]
    assert snapshots and snapshots[0]["odds"] == matches[0]["odds"]
    assert snapshots[0]["status"] == "fresh"


def test_maintenance_archives_completed_ucl_results_without_inventing_tips():
    now = datetime(2026, 9, 9, 20, tzinfo=timezone.utc)
    cache = MemoryCollection()
    archive = MemoryCollection()

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            return []

    provider = Provider()
    assert load_archive_from_db(archive) == {}
    result = run_maintenance(
        {"ucl2026": cache},
        provider,
        archive_collections={"ucl2026": archive},
        competition="ucl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: [{
            "id": "ucl-finished",
            "home_team": "Barcelona",
            "away_team": "Feyenoord Rotterdam",
            "commence_time": "2026-09-09T16:45:00Z",
            "round": "League Phase",
            "completed": True,
            "actual_score": "5:1",
        }],
    )

    assert result["status"] == "success"
    assert result["provider_calls"] == 1
    assert provider.calls == 1
    entry = archive.find_one({"_id": "ucl-finished"})
    assert entry["metadata"]["home_team"] == "Barcelona"
    assert entry["post_match_result"] == {
        "status": "completed",
        "actual_score": "5:1",
        "points_earned": None,
        "algo_points": None,
        "bot_points": {},
    }
    assert entry["prediction"]["top_tip"] is None
    assert "ucl-finished" in load_archive_from_db(archive)


def test_maintenance_reconstructs_missed_ucl_performance_from_clubelo():
    now = datetime(2026, 9, 9, 20, tzinfo=timezone.utc)
    cache = MemoryCollection()

    class ArchiveCollection(MemoryCollection):
        def replace_one(self, query, document, upsert=False):
            self.documents[query["_id"]] = dict(document)

    archive = ArchiveCollection()
    rows = [
        {"team_name": "Barcelona", "elo_rating": 1900.0},
        {"team_name": "Feyenoord", "elo_rating": 1750.0},
    ]

    result = run_maintenance(
        {"ucl2026": cache},
        type("Provider", (), {"get_competition_odds": lambda self, *args, **kwargs: []})(),
        archive_collections={"ucl2026": archive},
        competition="ucl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: [{
            "id": "ucl-finished",
            "home_team": "Barcelona",
            "away_team": "Feyenoord Rotterdam",
            "commence_time": "2026-09-09T16:45:00Z",
            "round": "League Phase",
            "completed": True,
            "actual_score": "5:1",
        }],
        clubelo_ingestor=lambda *args, **kwargs: {
            "status": "fresh", "source": "clubelo", "rows": rows,
        },
        math_engine=MathEngine("data/elo_ratings.csv", TEAM_MAPPING),
    )

    entry = archive.find_one({"_id": "ucl-finished"})
    assert result["reconstructed_results"] == 1
    assert entry["prediction"]["algo_reconstructed"] is True
    assert entry["prediction"]["source_mode"] == "elo-only"
    assert entry["prediction"]["top_tip"]
    assert entry["prediction"]["bots"]
    assert entry["post_match_result"]["algo_points"] is not None
    assert entry["post_match_result"]["bot_points"]


def test_maintenance_snapshot_is_the_input_for_t15_freeze():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=15)
    cache = MemoryCollection()
    archive = MemoryCollection([{
        "_id": "e1",
        "metadata": {
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
        },
        "prediction": {},
    }])

    class Provider:
        def get_competition_odds(self, competition, market):
            return [{
                "id": "e1",
                "home_team": "Bayern Munich",
                "away_team": "Arsenal",
                "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
                    {"name": "Bayern Munich", "price": "2.0"},
                    {"name": "Draw", "price": "3.2"},
                    {"name": "Arsenal", "price": "4.0"},
                ]}]}],
            }]

    run_maintenance(
        {"ucl2026": cache},
        Provider(),
        competition="ucl2026",
        now=now,
        fixture_fetcher=lambda **kwargs: [{
            "id": "e1",
            "home_team": "Bayern Munich",
            "away_team": "Arsenal",
            "commence_time": kickoff.isoformat(),
        }],
    )

    class Service:
        def predict(self, **kwargs):
            assert kwargs["odds"]["odds"] == {"home": 2.0, "draw": 3.2, "away": 4.0}
            return {
                "model_tip": "1:0",
                "top_tip": "1:0",
                "pool_tip": None,
                "pool_status": "unavailable",
                "status": "fresh",
                "source_status": "fresh",
                "source": "odds_api",
                "observed_at": kwargs["observed_at"],
                "source_mode": "odds-only",
                "model_version": "test",
                "context": kwargs["context"],
                "input_provenance": {},
                "provenance": {},
                "source_inputs": {"odds": kwargs["odds"], "elo": None},
            }

    frozen = freeze_prediction(cache, archive, Service(), "e1", competition="ucl2026", now=now)

    assert frozen["prediction"]["top_tip"] == "1:0"
    assert frozen["prediction"]["status"] == "fresh"


def test_expired_lease_takeover_requires_confirmed_owner_before_provider_call():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=14)
    lease_id = competition_document_id("ucl2026", "maintenance_lease")

    class LostRaceCollection(MemoryCollection):
        def update_one(self, query, update, upsert=False):
            self.documents[query["_id"]] = {"_id": query["_id"], "lease_token": "other-owner", "lease_until": (now + timedelta(minutes=5)).isoformat()}
            return type("Result", (), {"matched_count": 0})()

    cache = LostRaceCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": lease_id,
        "lease_until": (now - timedelta(minutes=1)).isoformat(),
        "lease_token": "expired-owner",
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            return []

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)

    assert result["status"] == "skipped"
    assert provider.calls == 0


def test_snapshot_status_boundary_rejects_unknown_values():
    with pytest.raises(ValueError, match="status"):
        append_odds_snapshot(
            MemoryCollection(),
            "ucl2026",
            "e1",
            "t15m",
            datetime.now(timezone.utc),
            {"home": 2.0, "draw": 3.0, "away": 4.0},
            status="partial",
        )


def test_wc_migration_is_copy_first_idempotent_and_preserves_tips():
    legacy_archive = MemoryCollection([{
        "_id": "match-1",
        "prediction": {"user_tip": "2:1"},
    }])
    legacy_cache = MemoryCollection([{"_id": "matches_cache", "data": [{"id": "match-1"}]}])
    legacy_bot = MemoryCollection([{"_id": "default", "name": "Legacy", "params": {"risk": 0.2}}])
    wc_archive, wc_cache, wc_bot = MemoryCollection(), MemoryCollection(), MemoryCollection()

    first = migrate_wc_legacy(
        legacy_archive,
        legacy_cache,
        legacy_bot,
        wc_archive_collection=wc_archive,
        wc_cache_collection=wc_cache,
        wc_custom_bot_collection=wc_bot,
    )
    second = migrate_wc_legacy(
        legacy_archive,
        legacy_cache,
        legacy_bot,
        wc_archive_collection=wc_archive,
        wc_cache_collection=wc_cache,
        wc_custom_bot_collection=wc_bot,
    )

    assert first["copied"] == 3
    assert second["copied"] == 0
    assert legacy_archive.find_one({"_id": "match-1"})["prediction"]["user_tip"] == "2:1"
    migrated = wc_archive.find_one({"_id": "match-1"})
    assert migrated["competition"] == "wc2026"
    assert migrated["schema_version"] == 1
    assert migrated["prediction"]["user_tip"] == "2:1"


def test_malformed_ucl_fixture_is_unavailable_without_schedule_validation():
    result = simulate_ucl_tournament(
        ["A"],
        [None],
        {},
        n_runs=1,
        validate_schedule=False,
    )

    assert result["status"] == "unavailable"
    assert result["reason"]
