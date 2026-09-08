from datetime import datetime, timedelta, timezone
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from src.competitions import competition_document_id
from src.routes.maintenance import init_router
from src.routes.matches import init_router as matches_router
from src.services import espn_data
from src.services.maintenance import run_maintenance
from src.services.snapshots import (
    BUCKET_OFFSETS,
    append_odds_snapshot,
    select_t15_snapshot,
)
from src.services.ucl_providers import (
    compose_match_sources,
    ingest_clubelo,
)
from src.odds_engine import OddsApiEngine
from src.odds_engine_apifootball import OddsApiEngine as ApiFootballOddsEngine
from src.routes.matches import build_elo_snapshot


class DuplicateKeyError(Exception):
    pass


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {}
        self.inserts = []
        for document in documents:
            self.documents[document["_id"]] = dict(document)

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        values = list(self.documents.values())
        if not query:
            return values
        return [doc for doc in values if all(doc.get(k) == v for k, v in query.items())]

    def insert_one(self, document):
        if document["_id"] in self.documents:
            raise DuplicateKeyError(document["_id"])
        self.documents[document["_id"]] = dict(document)
        self.inserts.append(dict(document))

    def update_one(self, query, update, upsert=False):
        key = query.get("_id")
        document = dict(self.documents.get(key, {"_id": key}))
        if "$set" in update:
            for field, value in update["$set"].items():
                target = document
                bits = field.split(".")
                for bit in bits[:-1]:
                    target = target.setdefault(bit, {})
                target[bits[-1]] = value
        if "$setOnInsert" in update and key not in self.documents:
            document.update(update["$setOnInsert"])
        if "$addToSet" in update:
            for field, value in update["$addToSet"].items():
                values = list(document.get(field, []))
                if value not in values:
                    values.append(value)
                document[field] = values
        self.documents[key] = document

    def delete_one(self, query):
        self.documents.pop(query.get("_id"), None)


class MongoRejectsImmutableId(MemoryCollection):
    def update_one(self, query, update, upsert=False):
        if any(field == "_id" or field.endswith("._id") for field in update.get("$set", {})):
            raise AssertionError("Mongo rejects _id in $set")
        super().update_one(query, update, upsert=upsert)


class OwnershipAwareCollection(MongoRejectsImmutableId):
    def delete_one(self, query):
        key = query.get("_id")
        document = self.documents.get(key)
        if document and all(document.get(field) == value for field, value in query.items()):
            self.documents.pop(key, None)


def _event(event_id, date):
    return {
        "id": event_id,
        "date": date,
        "season": {"slug": "league-phase"},
        "competitions": [{
            "status": {"type": {"completed": False, "detail": "Scheduled"}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Bayern Munich"}},
                {"homeAway": "away", "team": {"displayName": "Arsenal"}},
            ],
        }],
    }


def test_ucl_espn_windows_are_bounded_and_deduplicated(monkeypatch):
    calls = []
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        start = params["dates"][:8]
        if start == "20260901":
            return Response({"events": [_event("same", "2026-09-05T18:00:00Z")]})
        return Response({"events": [
            _event("same", "2026-09-05T18:00:00Z"),
            _event("other", "2026-09-10T18:00:00Z"),
        ]})

    monkeypatch.setattr(espn_data.requests, "get", fake_get)
    events = espn_data.get_scoreboard(
        competition="ucl2026",
        days_back=0,
        days_forward=10,
        now=base,
        chunk_days=7,
        use_cache=False,
    )

    assert {event["id"] for event in events} == {"same", "other"}
    assert len(calls) == 2
    assert calls[0][1]["dates"] == "20260901-20260907"
    assert calls[1][1]["dates"] == "20260908-20260911"
    assert all((int(call[1]["dates"][8:]) - int(call[1]["dates"][:8])) <= 7 for call in calls)
    assert all("uefa.champions" in call[0] for call in calls)


def test_clubelo_cache_contract_preserves_alias_and_provenance(monkeypatch):
    html = """
    <html><body><table id="ranking">
      <tr><th>Rank</th><th>Club</th><th>Elo</th></tr>
      <tr><td>1</td><td>Bayern Munich</td><td>1921</td></tr>
      <tr><td>2</td><td>Arsenal</td><td>1840</td></tr>
    </table></body></html>
    """
    cache = MemoryCollection()

    class Response:
        text = html
        content = html.encode()
        headers = {"etag": '"ucl"'}

        def raise_for_status(self):
            return None

    monkeypatch.setattr("src.services.ucl_providers.requests.get", lambda *args, **kwargs: Response())
    observed_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    document = ingest_clubelo(cache, competition="ucl2026", observed_at=observed_at)

    assert document["status"] == "fresh"
    assert document["source"] == "clubelo"
    assert document["observed_at"] == observed_at.isoformat()
    assert document["provenance"]["url"]
    assert {row["team"] for row in document["rows"]} == {"Bayern Munich", "Arsenal"}
    assert cache.find_one({"_id": competition_document_id("ucl2026", "clubelo_ratings")})["etag"] == '"ucl"'


def test_clubelo_persistence_never_sets_immutable_mongo_id(monkeypatch):
    html = "<table><tr><td>1</td><td>Arsenal</td><td>1840</td></tr></table>"

    class Response:
        text = html
        headers = {}

        def raise_for_status(self):
            return None

    cache = MongoRejectsImmutableId()
    document = ingest_clubelo(cache, competition="ucl2026", request_get=lambda *a, **k: Response())
    assert document["status"] == "fresh"
    assert cache.find_one({"_id": competition_document_id("ucl2026", "elo_ratings")})["rows"]


def test_clubelo_failure_is_truthful_and_does_not_create_ratings(monkeypatch):
    cache = MemoryCollection()

    def failed_get(*args, **kwargs):
        raise RuntimeError("ClubElo unavailable")

    document = ingest_clubelo(cache, competition="ucl2026", request_get=failed_get)
    assert document["status"] == "failed"
    assert document["rows"] == []
    assert "error" in document
    assert cache.find_one({"_id": competition_document_id("ucl2026", "clubelo_ratings")}) is None


def test_source_modes_are_explicit_when_provider_is_missing():
    assert compose_match_sources({"home": 2}, {"home": 1800})["source_mode"] == "odds+elo"
    assert compose_match_sources({"home": 2}, None)["source_mode"] == "odds-only"
    assert compose_match_sources(None, {"home": 1800})["source_mode"] == "elo-only"
    unavailable = compose_match_sources(None, None)
    assert unavailable["source_mode"] == "unavailable"
    assert unavailable["status"] == "unavailable"


def test_failed_or_empty_elo_is_not_a_present_source():
    result = compose_match_sources(
        {"home": 2.0, "draw": 3.2, "away": 4.0},
        {"status": "failed", "rows": [], "source": "clubelo"},
    )
    assert result["source_mode"] == "odds-only"
    assert result["source"] == "odds_api"


def test_odds_provider_uses_configurable_competition_identifier(monkeypatch):
    calls = []

    class Response:
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": "e1", "bookmakers": []}]

    def fake_get(url, params, timeout):
        calls.append((url, params))
        return Response()

    monkeypatch.setenv("ODDS_API_UCL2026_SPORT_KEY", "soccer_custom_ucl")
    monkeypatch.setattr("src.odds_engine.requests.get", fake_get)
    engine = object.__new__(OddsApiEngine)
    engine.api_key = "captured-key"
    engine._update_quota = lambda headers: None

    assert engine.get_competition_odds("ucl2026", market="h2h,totals")
    assert calls[0][0].endswith("/soccer_custom_ucl/odds")
    assert calls[0][1]["markets"] == "h2h,totals"


def test_append_only_snapshots_and_t15_selector_use_observation_time():
    cache = MemoryCollection()
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    first = append_odds_snapshot(
        cache,
        competition="ucl2026",
        event_id="e1",
        bucket="t24h",
        observed_at=kickoff - timedelta(hours=24),
        odds={"home": 2.0, "draw": 3.0, "away": 4.0},
    )
    second = append_odds_snapshot(
        cache,
        competition="ucl2026",
        event_id="e1",
        bucket="t15m",
        observed_at=kickoff - timedelta(minutes=10),
        odds={"home": 1.9, "draw": 3.1, "away": 4.2},
    )

    assert first["_id"] != second["_id"]
    assert len(cache.inserts) == 2
    selected = select_t15_snapshot(cache.inserts, kickoff)
    assert selected["odds"]["home"] == 2.0
    assert selected["bucket"] == "t24h"


def test_maintenance_missed_buckets_are_not_backfilled_and_bulk_call_is_capped():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=10)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat(), "home_team": "Bayern Munich", "away_team": "Arsenal"}],
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, competition, market):
            self.calls += 1
            return [{"id": "e1", "home_team": "Bayern Munich", "away_team": "Arsenal", "bookmakers": []}]

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=now)

    assert provider.calls == 1
    assert result["buckets"] == ["t24h", "t6h", "t75m", "t30m", "t15m"]
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "unavailable"
    assert state["events"]["e1"]["t24h"]["status"] == "unavailable"
    assert state["events"]["e1"]["t24h"]["error"] == "missed"
    assert all(
        state["events"]["e1"][bucket]["status"] in {"fresh", "stale", "unavailable", "failed"}
        for bucket in state["events"]["e1"]
    )
    assert [doc["bucket"] for doc in cache.inserts if "odds_snapshot" in doc["_id"]] == ["t15m"]
    again = run_maintenance(cache, provider, competition="ucl2026", now=now + timedelta(minutes=1))
    assert provider.calls == 1
    assert again["buckets"] == []


def test_force_maintenance_is_a_safe_noop():
    cache = MemoryCollection()

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("force must not call a provider")

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", force=True)
    assert result == {"status": "noop", "reason": "force_disabled", "provider_calls": 0, "mutated": False}
    assert cache.documents == {}


def test_no_due_bucket_does_not_spend_credits_or_write_snapshots():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            return []

    provider = Provider()
    result = run_maintenance(cache, provider, competition="ucl2026", now=kickoff - timedelta(days=3))
    assert result["provider_calls"] == 0
    assert provider.calls == 0
    assert not [doc for doc in cache.documents.values() if "snapshot" in doc.get("_id", "")]


def test_provider_failure_marks_bucket_failed_without_fabricating_odds():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            raise RuntimeError("Odds API failed")

    result = run_maintenance(cache, Provider(), competition="ucl2026", now=kickoff - timedelta(minutes=14))
    assert result["status"] == "failed"
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "failed"
    assert not [doc for doc in cache.documents.values() if "snapshot" in doc.get("_id", "")]


def test_captured_bucket_uses_fresh_status():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            return [{"id": "e1", "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}}]

    run_maintenance(cache, Provider(), competition="ucl2026", now=kickoff - timedelta(minutes=14))
    state = cache.find_one({"_id": competition_document_id("ucl2026", "odds_bucket_state")})
    assert state["events"]["e1"]["t15m"]["status"] == "fresh"


def test_live_maintenance_lease_is_a_unique_no_provider_claim():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=14)
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": competition_document_id("ucl2026", "maintenance_lease"),
        "lease_until": (now + timedelta(minutes=2)).isoformat(),
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


def test_expired_lease_replacement_does_not_delete_a_new_owner_lease():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    now = kickoff - timedelta(minutes=14)
    lease_id = competition_document_id("ucl2026", "maintenance_lease")
    cache = OwnershipAwareCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "e1", "commence_time": kickoff.isoformat()}],
    }, {
        "_id": lease_id,
        "lease_until": (now - timedelta(minutes=1)).isoformat(),
        "lease_token": "expired-owner",
    }])

    class Provider:
        def get_competition_odds(self, *args, **kwargs):
            cache.update_one(
                {"_id": lease_id},
                {"$set": {"lease_token": "renewed-owner", "lease_until": (now + timedelta(minutes=5)).isoformat()}},
            )
            return []

    run_maintenance(cache, Provider(), competition="ucl2026", now=now)
    assert cache.find_one({"_id": lease_id})["lease_token"] == "renewed-owner"


def test_public_match_force_is_cache_only():
    cache = MemoryCollection([{
        "_id": competition_document_id("ucl2026", "matches_cache"),
        "data": [{"id": "cached"}],
    }])

    class Provider:
        calls = 0

        def get_competition_odds(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("public force must not call a provider")

    class Engine:
        pass

    router = matches_router(Engine(), Provider(), {"ucl2026": cache}, {"ucl2026": MemoryCollection()})
    result = router.routes[0].endpoint(force=True, competition="ucl2026")
    assert result == [{"id": "cached"}]


def test_force_maintenance_validates_competition_before_noop():
    with pytest.raises(ValueError, match="Unknown competition"):
        run_maintenance({}, object(), competition="bad", force=True)


def test_maintenance_route_returns_http_400_for_unknown_competition():
    endpoint = init_router({"ucl2026": MemoryCollection()}, object(), cron_secret="test-secret").routes[0].endpoint
    scope = {
        "type": "http", "method": "POST", "path": "/api/internal/maintenance", "headers": [(b"authorization", b"Bearer test-secret")],
        "query_string": b"", "scheme": "http", "server": ("test", 80), "client": ("test", 1), "root_path": "", "http_version": "1.1",
    }
    with pytest.raises(Exception) as exc_info:
        endpoint(Request(scope), competition="bad")
    assert getattr(exc_info.value, "status_code", None) == 400


def test_ucl_unknown_clubs_have_no_synthetic_elo_snapshot():
    class Engine:
        elo_df = type("Frame", (), {"team_name": []})()

    assert build_elo_snapshot(Engine(), "Unknown Home", "Unknown Away", "ucl2026") is None


def test_api_football_ucl_quotes_use_ucl_sport_key(monkeypatch):
    fixture = {
        "fixture": {"id": 1, "date": "2026-09-10T18:00:00Z"},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Bayern Munich"}},
        "league": {"round": "League Phase"},
    }
    odd = {
        "fixture": {"id": 1},
        "bookmakers": [{"id": 1, "name": "Book", "bets": [{"id": 1, "values": [
            {"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.0"}, {"value": "Away", "odd": "4.0"}
        ]}]}],
    }
    engine = object.__new__(ApiFootballOddsEngine)
    engine._request = lambda path, params: {"response": [fixture] if path == "/fixtures" else [odd]}
    assert engine.get_competition_odds("ucl2026")[0]["sport_key"] == "soccer_uefa_champs_league"


def test_maintenance_route_requires_bearer_secret_and_supports_idempotency():
    cache = MemoryCollection()

    class Provider:
        calls = 0

        def get_competition_odds(self, competition, market):
            self.calls += 1
            return []

    provider = Provider()
    endpoint = init_router({"ucl2026": cache}, provider, cron_secret="test-secret").routes[0].endpoint

    def request(headers):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/internal/maintenance",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "query_string": b"force=true",
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1),
            "root_path": "",
            "http_version": "1.1",
        }
        return Request(scope)

    with pytest.raises(Exception) as missing:
        endpoint(request({}))
    assert getattr(missing.value, "status_code", None) == 401
    with pytest.raises(Exception) as wrong:
        endpoint(request({"Authorization": "Bearer wrong"}))
    assert getattr(wrong.value, "status_code", None) == 401
    response = endpoint(request({"Authorization": "Bearer test-secret"}), force=True)
    assert response["provider_calls"] == 0
    assert provider.calls == 0
