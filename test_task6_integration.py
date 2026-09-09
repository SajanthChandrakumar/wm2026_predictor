from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess

import pytest

from test_task2_providers import MemoryCollection
from src.competitions import competition_document_id
from src.routes.matches import init_router as matches_router
from src.services.maintenance import run_maintenance
from src.services.migration import migrate_wc_legacy
from src.services.prediction import freeze_prediction
from src.services.elo_sync import perform_elo_sync
from src.services.snapshots import append_odds_snapshot
from src.services.ucl_simulation import simulate_ucl_tournament


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


def test_migration_script_direct_invocation_bootstraps_repo_imports_and_dotenv():
    repo = Path(__file__).resolve().parent
    env = os.environ.copy()
    env.pop("MONGO_URI", None)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(repo / ".venv/bin/python"), "scripts/migrate_wc_legacy.py"],
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
