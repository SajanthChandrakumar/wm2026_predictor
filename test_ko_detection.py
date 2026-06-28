import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
from src.constants import _is_ko_round


class TestIsKoRound:
    @pytest.mark.parametrize("round_str", [
        "Round of 16",
        "Quarter-finals",
        "Semi-finals",
        "Final",
        "3rd Place Final",
        "round of 16",
        "QUARTER-FINALS",
    ])
    def test_ko_rounds_detected(self, round_str):
        assert _is_ko_round(round_str) is True

    @pytest.mark.parametrize("round_str", [
        "Group A - 1",
        "Group B - 2",
        "Group F - 3",
        "",
    ])
    def test_group_rounds_not_ko(self, round_str):
        assert _is_ko_round(round_str) is False

    def test_none_returns_false(self):
        assert _is_ko_round(None) is False
