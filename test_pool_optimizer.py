import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from src.math_engine import MathEngine


@pytest.fixture
def engine():
    return MathEngine("data/elo_ratings.csv")


@pytest.fixture
def score_matrix():
    """A realistic score matrix from xG ≈ 1.5 home, 1.1 away."""
    return MathEngine.generate_exact_score_matrix(1.5, 1.1, max_goals=10)


class TestExpectedPoints:
    def test_returns_dataframe_with_correct_columns(self, engine, score_matrix):
        df = engine.calculate_expected_points(score_matrix, is_ko_phase=False)
        assert isinstance(df, pd.DataFrame)
        assert "Tipp" in df.columns
        assert "xP" in df.columns

    def test_returns_top_n(self, engine, score_matrix):
        df = engine.calculate_expected_points(score_matrix, is_ko_phase=False, top_n=3)
        assert len(df) == 3

    def test_tips_sorted_descending(self, engine, score_matrix):
        df = engine.calculate_expected_points(score_matrix, is_ko_phase=False, top_n=10)
        xps = df["xP"].tolist()
        assert xps == sorted(xps, reverse=True)

    def test_all_xp_non_negative(self, engine, score_matrix):
        df = engine.calculate_expected_points(score_matrix, is_ko_phase=False, top_n=36)
        assert all(df["xP"] >= 0)

    def test_deterministic_result_gives_exact_10(self, engine):
        """100% probability on 2:1 → tipping 2:1 must yield exactly 10 xP."""
        m = pd.DataFrame(np.zeros((6, 6)),
                         index=[str(i) for i in range(6)],
                         columns=[str(i) for i in range(6)])
        m.loc["2", "1"] = 1.0
        df = engine.calculate_expected_points(m, is_ko_phase=False)
        assert df.iloc[0]["Tipp"] == "2:1"
        assert df.iloc[0]["xP"] == 10.0

    def test_ko_phase_doubles_points(self, engine):
        """KO multiplier: same scenario must yield 20 xP in KO phase."""
        m = pd.DataFrame(np.zeros((6, 6)),
                         index=[str(i) for i in range(6)],
                         columns=[str(i) for i in range(6)])
        m.loc["2", "1"] = 1.0
        df = engine.calculate_expected_points(m, is_ko_phase=True)
        assert df.iloc[0]["xP"] == 20.0

    def test_home_favourite_prefers_home_win(self, engine):
        """When home has much higher xG, top tip should be a home win."""
        sm = MathEngine.generate_exact_score_matrix(2.5, 0.7, max_goals=10)
        df = engine.calculate_expected_points(sm, is_ko_phase=False, top_n=1)
        tip = df.iloc[0]["Tipp"]
        h, a = map(int, tip.split(":"))
        assert h > a

    def test_symmetric_xg_prefers_draw_or_narrow(self, engine):
        """Equal xG: top tip should be a draw or very narrow result."""
        sm = MathEngine.generate_exact_score_matrix(1.2, 1.2, max_goals=10)
        df = engine.calculate_expected_points(sm, is_ko_phase=False, top_n=1)
        tip = df.iloc[0]["Tipp"]
        h, a = map(int, tip.split(":"))
        assert abs(h - a) <= 1


class TestPointsDistribution:
    def test_returns_mean_and_std(self, engine, score_matrix):
        ev, std = engine._points_distribution(1, 0, score_matrix, is_ko_phase=False)
        assert isinstance(ev, float)
        assert isinstance(std, float)
        assert std >= 0

    def test_perfect_tip_has_zero_std(self, engine):
        """100% on one outcome → no variance."""
        m = pd.DataFrame(np.zeros((6, 6)),
                         index=[str(i) for i in range(6)],
                         columns=[str(i) for i in range(6)])
        m.loc["1", "0"] = 1.0
        ev, std = engine._points_distribution(1, 0, m, is_ko_phase=False)
        assert std == 0.0
        assert ev == 10.0


class TestCalculateActualPoints:
    def test_exact_match(self):
        assert MathEngine.calculate_actual_points("2:1", "2:1") == 10

    def test_tendency_only(self):
        assert MathEngine.calculate_actual_points("3:0", "2:1") == 5

    def test_tendency_plus_one_goal(self):
        assert MathEngine.calculate_actual_points("2:0", "2:1") == 6

    def test_tendency_plus_diff(self):
        assert MathEngine.calculate_actual_points("3:1", "2:0") == 8

    def test_wrong_tendency(self):
        assert MathEngine.calculate_actual_points("2:0", "0:1") == 0

    def test_draw_exact(self):
        assert MathEngine.calculate_actual_points("1:1", "1:1") == 10

    def test_draw_tendency_wrong_goals(self):
        assert MathEngine.calculate_actual_points("0:0", "1:1") == 8

    def test_ko_doubles(self):
        assert MathEngine.calculate_actual_points("2:1", "2:1", is_ko_phase=True) == 20

    def test_invalid_tip_returns_zero(self):
        assert MathEngine.calculate_actual_points("abc", "2:1") == 0
