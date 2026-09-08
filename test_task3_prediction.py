from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.math_engine import MathEngine
from src.services.prediction import (
    MatchContext,
    PredictionService,
    advancement_probabilities,
    build_aet_distribution,
    build_match_context,
    extra_time_eligible_for_score,
    pool_lambda,
    pool_tip_from_field,
    freeze_prediction,
    user_tip_is_open,
)


class MemoryCollection:
    def __init__(self, documents=()):
        self.documents = {doc["_id"]: dict(doc) for doc in documents}
        self.replacements = 0

    def find_one(self, query):
        return self.documents.get(query.get("_id"))

    def find(self, query=None):
        values = list(self.documents.values())
        if not query:
            return values
        return [doc for doc in values if all(doc.get(key) == value for key, value in query.items())]

    def replace_one(self, query, document, upsert=False):
        self.documents[query["_id"]] = dict(document)
        self.replacements += 1


def _matrix(cells, size=4):
    values = np.zeros((size, size), dtype=float)
    for (home, away), probability in cells.items():
        values[home, away] = probability
    return pd.DataFrame(values, index=[str(i) for i in range(size)], columns=[str(i) for i in range(size)])


def _engine():
    return MathEngine("data/elo_ratings.csv")


def test_context_derives_second_leg_and_final_extra_time_rules():
    second = build_match_context({
        "stage": "round_of_16",
        "tie_id": "tie-1",
        "leg": "second",
        "first_leg_score": "1:0",
    }, competition="ucl2026")
    assert isinstance(second, MatchContext)
    assert second.stage == "round_of_16"
    assert second.tie_id == "tie-1"
    assert second.leg == "second"
    assert extra_time_eligible_for_score(second, 0, 1)
    assert not extra_time_eligible_for_score(second, 1, 1)

    final = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    assert extra_time_eligible_for_score(final, 1, 1)
    assert not extra_time_eligible_for_score(final, 2, 1)

    first = build_match_context({"stage": "round_of_16", "leg": "first", "first_leg_score": "0:0"}, competition="ucl2026")
    assert not extra_time_eligible_for_score(first, 0, 0)


def test_aet_convolves_only_aggregate_tie_cells_and_stays_normalized():
    base = _matrix({(2, 2): 0.4, (0, 1): 0.6})
    context = build_match_context({"stage": "round_of_16", "leg": "second", "first_leg_score": "0:0"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.2, 0.9, context)

    assert result.loc["0", "1"] == pytest.approx(0.6)
    assert result.loc["2", "2"] < 0.4
    assert float(result.to_numpy().sum()) == pytest.approx(1.0)


def test_final_aet_only_changes_90_minute_draw_cells():
    base = _matrix({(2, 2): 0.5, (0, 1): 0.5})
    context = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.0, 1.0, context)
    assert result.loc["0", "1"] == pytest.approx(0.5)
    assert result.loc["2", "2"] < 0.5


def test_penalty_advancement_is_separate_from_srf_score_distribution():
    base = _matrix({(1, 1): 1.0})
    context = build_match_context({"stage": "final", "leg": "single"}, competition="ucl2026")
    result = build_aet_distribution(base, 1.0, 1.0, context)
    assert advancement_probabilities(context, 1, 1) == {"home": 0.5, "away": 0.5}
    assert result.loc["1", "1"] < 1.0
    assert all(value >= 0 for value in result.to_numpy().ravel())


def test_pool_lambda_uses_leader_gap_and_remaining_srf_points():
    assert pool_lambda(user_points=80, leader_points=100, remaining_srf_max_points=50) == pytest.approx(0.24)
    assert pool_lambda(user_points=100, leader_points=80, remaining_srf_max_points=50) == 0.0
    assert pool_lambda(user_points=0, leader_points=100, remaining_srf_max_points=1) == 0.6


def test_pool_tip_uses_field_counts_and_returns_expected_tip():
    matrix = _matrix({(0, 0): 0.5, (2, 0): 0.5})
    result = pool_tip_from_field(
        matrix,
        field_counts={"0:0": 3, "2:0": 1},
        user_points=0,
        leader_points=20,
        remaining_srf_max_points=100,
    )
    assert result["tip"] in {"0:0", "2:0"}
    assert result["lambda"] == pytest.approx(0.12)
    assert result["field_count"] == 4


def test_invalid_field_counts_only_disable_pool_tip():
    service = PredictionService(_engine())
    result = service.predict(
        odds={"home": 2.0, "draw": 3.2, "away": 4.0},
        elo=None,
        competition="ucl2026",
        context={"stage": "league", "leg": "single"},
        field_counts={"not-a-score": 3},
        user_points=0,
        leader_points=10,
        remaining_srf_max_points=100,
    )
    assert result["source_mode"] == "odds-only"
    assert result["model_tip"]
    assert result["top_tip"] == result["model_tip"]
    assert result["pool_tip"] is None
    assert result["pool_status"] == "unavailable"
    assert result["model_version"]
    assert result["input_provenance"]


def test_freeze_uses_latest_eligible_t15_snapshot_and_is_idempotent():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    cache = MemoryCollection([
        {"_id": "ucl2026:matches_cache", "data": [{"id": "m1", "commence_time": kickoff.isoformat()}]},
        {
            "_id": "ucl2026:odds_snapshot:m1:t24h:1",
            "event_id": "m1", "bucket": "t24h", "status": "fresh",
            "observed_at": (kickoff - timedelta(hours=24)).isoformat(),
            "odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
        },
        {
            "_id": "ucl2026:odds_snapshot:m1:t15m:2",
            "event_id": "m1", "bucket": "t15m", "status": "fresh",
            "observed_at": (kickoff - timedelta(minutes=15)).isoformat(),
            "odds": {"home": 1.8, "draw": 3.4, "away": 4.6},
        },
    ])
    archive = MemoryCollection([{"_id": "m1", "metadata": {"commence_time": kickoff.isoformat()}, "prediction": {}}])
    service = PredictionService(_engine())
    frozen = freeze_prediction(
        cache,
        archive,
        service,
        "m1",
        competition="ucl2026",
        now=kickoff - timedelta(minutes=10),
    )
    assert frozen["prediction"]["frozen_at"]
    assert frozen["prediction"]["model_tip"] == frozen["prediction"]["top_tip"]
    assert frozen["prediction"]["source_inputs"]["odds"]["home"] == 1.8
    writes = archive.replacements
    again = freeze_prediction(
        cache,
        archive,
        service,
        "m1",
        competition="ucl2026",
        now=kickoff - timedelta(minutes=9),
    )
    assert again == frozen
    assert archive.replacements == writes


def test_user_tip_closes_at_t5_but_undated_legacy_entry_stays_open():
    kickoff = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    assert user_tip_is_open(kickoff.isoformat(), kickoff - timedelta(minutes=6))
    assert not user_tip_is_open(kickoff.isoformat(), kickoff - timedelta(minutes=5))
    assert user_tip_is_open(None, kickoff)
    assert user_tip_is_open("not-a-time", kickoff)
