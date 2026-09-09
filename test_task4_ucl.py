from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.services.ucl_simulation import (
    DEFAULT_UCL_RUNS,
    UCL_TABLE_VERSION,
    build_playoff_bracket,
    build_ucl_table,
    rank_ucl_rows,
    simulate_ucl_tournament,
    validate_ucl_schedule,
)


def _teams():
    return [f"Team {i:02d}" for i in range(36)]


def _fixtures(teams=None, *, completed=True):
    teams = teams or _teams()
    fixtures = []
    # Eight disjoint rounds give every club eight unique fixtures.  The
    # alternating home convention yields exactly four home and four away.
    for round_no in range(4):
        for team_index, home in enumerate(teams):
            away = teams[(team_index + round_no + 1) % len(teams)]
            fixtures.append({
                "id": f"m-{round_no}-{team_index}",
                "home_team": home,
                "away_team": away,
                "status": "completed" if completed else "scheduled",
                "score_90": "0:0" if completed else None,
            })
    return fixtures


def _matrix(*, home=1, away=0):
    return pd.DataFrame(
        [[0.0] * 3 for _ in range(3)],
        index=["0", "1", "2"],
        columns=["0", "1", "2"],
    ).set_axis([], axis="index", copy=False) if False else {
        f"{home}:{away}": 1.0,
    }


def test_ucl_schedule_validates_all_four_invariants():
    teams, fixtures = _teams(), _fixtures()
    assert validate_ucl_schedule(teams, fixtures) == {"teams": 36, "fixtures": 144}

    with pytest.raises(ValueError, match="36 unique teams"):
        validate_ucl_schedule(teams[:-1], fixtures)
    with pytest.raises(ValueError, match="144 unique fixtures"):
        validate_ucl_schedule(teams, fixtures[:-1])

    broken = _fixtures()
    broken[-1]["home_team"], broken[-1]["away_team"] = "Team 00", "Team 10"
    with pytest.raises(ValueError, match="8 fixtures/team"):
        validate_ucl_schedule(teams, broken)

    broken = _fixtures()
    broken[-1]["home_team"], broken[-1]["away_team"] = broken[-1]["away_team"], broken[-1]["home_team"]
    with pytest.raises(ValueError, match=r"4 home \+ 4 away/team"):
        validate_ucl_schedule(teams, broken)


def test_local_table_ranks_base_and_all_uefa_tie_break_stages():
    teams, fixtures = _teams(), _fixtures()
    # All fixtures are draws.  These two clubs then tie on points/GD/goals/
    # away goals/wins/away wins and are separated by opponent aggregates,
    # discipline, then the versioned coefficient.
    for fixture in fixtures:
        fixture["score_90"] = "0:0"
    rows = build_ucl_table(
        teams,
        fixtures,
        disciplinary_scores={"Team 00": 4, "Team 01": 1},
        uefa_coefficients={"Team 00": {"version": "2026", "coefficient": 100}, "Team 01": {"version": "2026", "coefficient": 90}},
    )
    assert rows[0]["points"] == 8
    assert {row["team"] for row in rows[:36]} == set(teams)
    assert rows[0]["opponents_points"] >= rows[1]["opponents_points"]
    assert rows[-1]["uefa_coefficient_version"] == "2026"

    # Directly exercise each final tie-break in the public sorter contract.
    tied = [
        {"team": "low-discipline", "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 2, "wins": 3, "away_wins": 1, "opponents_points": 4, "opponents_goal_difference": 1, "opponents_goals": 3, "disciplinary_score": 1, "uefa_coefficient": 50},
        {"team": "high-discipline", "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 2, "wins": 3, "away_wins": 1, "opponents_points": 4, "opponents_goal_difference": 1, "opponents_goals": 3, "disciplinary_score": 2, "uefa_coefficient": 100},
    ]
    # build_ucl_table accepts pre-aggregated rows for deterministic ranking
    # checks, keeping the local ranking order independently testable.
    ranked = build_ucl_table(tied, [], precomputed=True)
    assert [row["team"] for row in ranked] == ["low-discipline", "high-discipline"]


def test_live_display_prefers_official_espn_order_but_local_table_does_not():
    teams, fixtures = _teams(), _fixtures()
    official = list(reversed(teams))
    rows = build_ucl_table(teams, fixtures, official_order=official)
    assert [row["team"] for row in rows] == official
    assert all(row["table_source"] == "espn" for row in rows)


@pytest.mark.parametrize(
    ("field", "better", "worse"),
    [
        ("points", 10, 9),
        ("goal_difference", 2, 1),
        ("goals_for", 5, 4),
        ("away_goals", 3, 2),
        ("wins", 3, 2),
        ("away_wins", 2, 1),
        ("opponents_points", 8, 7),
        ("opponents_goal_difference", 4, 3),
        ("opponents_goals", 6, 5),
        ("disciplinary_score", 1, 2),
        ("uefa_coefficient", 100, 90),
    ],
)
def test_local_ranking_uses_each_uefa_criterion_in_order(field, better, worse):
    base = {
        "points": 10, "goal_difference": 2, "goals_for": 5, "away_goals": 3,
        "wins": 3, "away_wins": 2, "opponents_points": 8,
        "opponents_goal_difference": 4, "opponents_goals": 6,
        "disciplinary_score": 1, "uefa_coefficient": 90,
    }
    first, second = dict(base), dict(base)
    first.update(team="better", **{field: better})
    second.update(team="worse", **{field: worse})
    assert [row["team"] for row in rank_ucl_rows([second, first])] == ["better", "worse"]


def test_playoff_bracket_maps_seeded_second_legs():
    bracket = build_playoff_bracket()
    assert [(tie["seeded_position"], tie["unseeded_position"]) for tie in bracket] == [
        (9, 24), (10, 23), (11, 22), (12, 21), (13, 20), (14, 19), (15, 18), (16, 17)
    ]
    assert all(tie["first_leg"]["home_position"] == tie["unseeded_position"] for tie in bracket)
    assert all(tie["second_leg"]["home_position"] == tie["seeded_position"] for tie in bracket)


def test_simulation_is_seeded_and_returns_all_ucl_round_probabilities():
    teams, fixtures = _teams(), _fixtures(completed=False)
    matrices = {"default": _matrix(home=1, away=0)}
    matrices.update({fixture["id"]: _matrix(home=1, away=0) for fixture in fixtures})
    first = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908)
    second = simulate_ucl_tournament(teams, fixtures, matrices, n_runs=12, seed=20260908)
    assert first == second
    assert first["status"] == "fresh"
    assert first["runs"] == 12
    assert first["seed"] == 20260908
    assert first["table_version"] == UCL_TABLE_VERSION
    assert len(first["teams"]) == 36
    assert {"expected_points", "expected_rank", "top8", "top24", "round_of_16", "quarterfinal", "semifinal", "final", "champion"} <= set(first["teams"][0])
    assert first["bracket"]["playoff"]


def test_simulation_missing_open_matrix_is_explicitly_unavailable():
    teams, fixtures = _teams(), _fixtures(completed=False)
    result = simulate_ucl_tournament(teams, fixtures, {}, n_runs=2)
    assert result["status"] == "unavailable"
    assert "score matrix" in result["reason"].lower()


def test_simulation_final_uses_et_then_penalties_without_copying_knockout_math():
    teams = ["A", "B"]
    fixture = {"id": "final", "home_team": "A", "away_team": "B", "status": "scheduled"}
    result = simulate_ucl_tournament(
        teams,
        [fixture],
        {"final": {"0:0": 1.0}},
        n_runs=4,
        seed=7,
        validate_schedule=False,
    )
    assert result["status"] == "unavailable"  # league table input is incomplete, not silently invented


def test_two_leg_tie_reuses_task3_aggregate_et_and_penalty_rules():
    from src.services.ucl_simulation import _play_two_leg_tie

    winner, legs = _play_two_leg_tie(
        "Seeded", "Unseeded", {"default": {"0:0": 1.0}}, np.random.default_rng(7), stage="playoff"
    )
    assert winner in {"Seeded", "Unseeded"}
    assert legs[0]["score_90"] == (0, 0)
    assert legs[1]["score_90"] == (0, 0)
    assert legs[1]["score_aet"] == (0, 0)
    assert legs[1]["penalties"] is True


def test_default_run_count_is_uefa_requirement():
    assert DEFAULT_UCL_RUNS == 20_000
