import importlib.util
from pathlib import Path

CFB_EXAMPLE = Path(__file__).parent.parent / "examples" / "cfb.py"


def load_cfb_example():
    spec = importlib.util.spec_from_file_location("cfb_example", CFB_EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_moneylines_uses_american_odds():
    cfb = load_cfb_example()
    games = [{"winner_ml": "+121", "loser_ml": "-149", "winner_odds": 2.21, "loser_odds": 1.671}]

    normalized = cfb.normalize_moneylines(games)

    assert normalized[0]["winner_odds"] == 121
    assert normalized[0]["loser_odds"] == -149


def test_normalize_moneylines_removes_both_odds_when_either_moneyline_is_invalid():
    cfb = load_cfb_example()
    games = [{"winner_ml": "+121", "loser_ml": "-", "winner_odds": 2.21, "loser_odds": 1.671}]

    normalized = cfb.normalize_moneylines(games)

    assert "winner_odds" not in normalized[0]
    assert "loser_odds" not in normalized[0]
