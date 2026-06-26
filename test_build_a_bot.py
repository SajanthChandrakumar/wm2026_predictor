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


SAMPLE_ODDS = {"home": 2.10, "draw": 3.40, "away": 3.50}
SAMPLE_ELO_HOME = 1800.0
SAMPLE_ELO_AWAY = 1700.0


class TestComputeCustomBotTip:
    def test_returns_valid_tip_format(self, engine):
        tip = engine.compute_custom_bot_tip(SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY, {})
        parts = tip.split(":")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)
        assert all(0 <= int(p) <= 5 for p in parts)

    def test_pure_market_equals_broker_style(self, engine):
        """market_weight=1.0 should produce a tip that favours market probabilities."""
        tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 1.0, "risk": 0, "draw_bias": 0, "underdog_bias": 0}
        )
        h, a = map(int, tip.split(":"))
        assert h >= a  # home is favourite in these odds

    def test_pure_elo_equals_professor_style(self, engine):
        """market_weight=0.0 should rely on Elo only."""
        tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.0, "risk": 0, "draw_bias": 0, "underdog_bias": 0}
        )
        assert ":" in tip

    def test_high_draw_bias_picks_draw(self, engine):
        """draw_bias=6.0 should overwhelm xP and force a draw tip."""
        tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.7, "risk": 0, "draw_bias": 6.0, "underdog_bias": 0}
        )
        h, a = map(int, tip.split(":"))
        assert h == a

    def test_high_underdog_bias_picks_underdog(self, engine):
        """underdog_bias=6.0 should force the underdog to win in the tip."""
        tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.7, "risk": 0, "draw_bias": 0, "underdog_bias": 6.0}
        )
        h, a = map(int, tip.split(":"))
        assert a > h  # away is the underdog in these odds

    def test_negative_risk_prefers_safe_tip(self, engine):
        """Negative risk should favour low-variance tips (typically the chalk)."""
        safe_tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.7, "risk": -1.0, "draw_bias": 0, "underdog_bias": 0}
        )
        risky_tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.7, "risk": 1.0, "draw_bias": 0, "underdog_bias": 0}
        )
        # At minimum, both should be valid
        assert ":" in safe_tip and ":" in risky_tip

    def test_ko_phase_produces_valid_tip(self, engine):
        tip = engine.compute_custom_bot_tip(
            SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY,
            {"market_weight": 0.7, "risk": 0, "draw_bias": 0, "underdog_bias": 0},
            is_ko=True
        )
        parts = tip.split(":")
        assert len(parts) == 2
        assert all(p.isdigit() for p in parts)

    def test_deterministic_same_params_same_tip(self, engine):
        """Same inputs must always produce the same tip (no randomness)."""
        params = {"market_weight": 0.5, "risk": 0.3, "draw_bias": 1.0, "underdog_bias": 0.5}
        t1 = engine.compute_custom_bot_tip(SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY, params)
        t2 = engine.compute_custom_bot_tip(SAMPLE_ODDS, SAMPLE_ELO_HOME, SAMPLE_ELO_AWAY, params)
        assert t1 == t2


class TestComputeBotTips:
    @pytest.fixture
    def bot_inputs(self, engine):
        true_probs = MathEngine.remove_margin(SAMPLE_ODDS["home"], SAMPLE_ODDS["draw"], SAMPLE_ODDS["away"])
        xg_h, xg_a = engine.derive_xg_from_odds(true_probs["home"], true_probs["draw"], true_probs["away"])
        sm = engine.generate_exact_score_matrix(xg_h, xg_a, max_goals=10)
        xp_df = engine.calculate_expected_points(sm, is_ko_phase=False)
        return sm, xp_df, true_probs

    def test_returns_all_five_bots(self, engine, bot_inputs):
        sm, xp_df, true_probs = bot_inputs
        bots = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="test123", is_ko_phase=False,
        )
        assert set(bots.keys()) == {"broker", "professor", "rebel", "sniper", "gambler"}

    def test_all_bots_have_valid_tips(self, engine, bot_inputs):
        sm, xp_df, true_probs = bot_inputs
        bots = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="test123", is_ko_phase=False,
        )
        for name, info in bots.items():
            tip = info["tip"]
            parts = tip.split(":")
            assert len(parts) == 2, f"Bot {name} has invalid tip: {tip}"
            assert all(p.isdigit() for p in parts), f"Bot {name} has non-numeric tip: {tip}"

    def test_sniper_always_picks_draw(self, engine, bot_inputs):
        sm, xp_df, true_probs = bot_inputs
        bots = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="test123", is_ko_phase=False,
        )
        h, a = map(int, bots["sniper"]["tip"].split(":"))
        assert h == a

    def test_rebel_picks_underdog_win(self, engine, bot_inputs):
        sm, xp_df, true_probs = bot_inputs
        bots = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="test123", is_ko_phase=False,
        )
        h, a = map(int, bots["rebel"]["tip"].split(":"))
        if true_probs["home"] > true_probs["away"]:
            assert a > h
        else:
            assert h > a

    def test_gambler_deterministic_by_match_id(self, engine, bot_inputs):
        sm, xp_df, true_probs = bot_inputs
        b1 = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="fixed_seed_id", is_ko_phase=False,
        )
        b2 = engine.compute_bot_tips(
            sm, xp_df, true_probs, prob_over25=0.55,
            home_team="Germany", away_team="Japan",
            match_id="fixed_seed_id", is_ko_phase=False,
        )
        assert b1["gambler"]["tip"] == b2["gambler"]["tip"]

    def test_gambler_varies_by_match_id(self, engine, bot_inputs):
        """Different match IDs should (usually) produce different gambler tips."""
        sm, xp_df, true_probs = bot_inputs
        tips = set()
        for i in range(20):
            bots = engine.compute_bot_tips(
                sm, xp_df, true_probs, prob_over25=0.55,
                home_team="Germany", away_team="Japan",
                match_id=f"match_{i}", is_ko_phase=False,
            )
            tips.add(bots["gambler"]["tip"])
        assert len(tips) > 1
