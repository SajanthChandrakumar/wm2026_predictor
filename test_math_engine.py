import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.math_engine import MathEngine

@pytest.fixture
def math_engine():
    # We can mock the CSV by creating a tiny dummy file or just testing methods that don't need it.
    # For testing get_elo_probability and static methods, the CSV content doesn't matter unless we call merge_odds_and_elo.
    dummy_csv = "data/elo_ratings.csv" 
    return MathEngine(dummy_csv)

def test_remove_margin():
    odds = MathEngine.remove_margin(2.5, 3.2, 2.8)
    assert "home" in odds
    assert "draw" in odds
    assert "away" in odds
    assert abs(odds["home"] + odds["draw"] + odds["away"] - 1.0) < 1e-6

def test_get_elo_probability(math_engine):
    # Equal ratings -> 0.5 probability
    prob = math_engine.get_elo_probability(1500, 1500)
    assert prob == 0.5
    
    # Higher rating -> higher probability
    prob2 = math_engine.get_elo_probability(1600, 1500)
    assert prob2 > 0.5

def test_derive_xg_from_odds():
    # If probs are completely symmetrical, xG should be roughly identical
    xg_home, xg_away = MathEngine.derive_xg_from_odds(0.4, 0.2, 0.4, 0.5)
    assert abs(xg_home - xg_away) < 0.1

def test_generate_exact_score_matrix():
    matrix = MathEngine.generate_exact_score_matrix(1.5, 1.2, max_goals=3)
    assert isinstance(matrix, pd.DataFrame)
    assert matrix.shape == (4, 4)
    # Total probability up to 3 goals should be less than 1, but individually valid
    assert (matrix.values >= 0).all() and (matrix.values <= 1).all()

def test_calculate_expected_points(math_engine):
    # Create a dummy 6x6 score matrix with 100% probability on 2:1
    matrix = pd.DataFrame(np.zeros((6, 6)), index=[str(i) for i in range(6)], columns=[str(i) for i in range(6)])
    matrix.loc["2", "1"] = 1.0 
    
    xp_df = math_engine.calculate_expected_points(matrix, is_ko_phase=False)
    
    assert isinstance(xp_df, pd.DataFrame)
    assert len(xp_df) == 5
    assert "Tipp" in xp_df.columns
    assert "xP" in xp_df.columns
    
    # The best tip should be 2:1, earning exactly 10 points (5 for tendency, 1 for home, 1 for away, 3 for diff)
    assert xp_df.iloc[0]["Tipp"] == "2:1"
    assert xp_df.iloc[0]["xP"] == 10.0
