import math

import pytest

from keeks_elote import score_projections

DATA = {
    1: [{"winner": "A", "loser": "B"}, {"winner": "C", "loser": "D"}],
}


def _proj(winner, loser, probability, period=1):
    return {"period": period, "predicted_winner": winner, "predicted_loser": loser, "probability": probability}


def test_exact_values_one_right_one_wrong():
    result = score_projections([_proj("A", "B", 0.8), _proj("D", "C", 0.6)], DATA)
    assert result["n"] == 2
    assert result["skipped"] == 0
    assert result["accuracy"] == 0.5
    assert result["log_loss"] == pytest.approx(-(math.log(0.8) + math.log(0.4)) / 2)
    assert result["brier"] == pytest.approx(((0.8 - 1) ** 2 + (0.6 - 0) ** 2) / 2)
    assert result["brier"] == pytest.approx(0.2)
    assert result["min_probability"] == 0.6
    assert result["max_probability"] == 0.8


def test_outcome_join_is_not_flipped():
    right = score_projections([_proj("A", "B", 0.9)], DATA)
    wrong = score_projections([_proj("B", "A", 0.9)], DATA)
    assert right["accuracy"] == 1.0
    assert right["brier"] == pytest.approx(0.01)
    assert wrong["accuracy"] == 0.0
    assert wrong["brier"] == pytest.approx(0.81)
    assert wrong["log_loss"] == pytest.approx(-math.log(0.1))


def test_unmatched_projection_is_skipped_not_dropped():
    result = score_projections([_proj("A", "B", 0.7), _proj("A", "B", 0.7, period=9), _proj("X", "Y", 0.7)], DATA)
    assert result["n"] == 1
    assert result["skipped"] == 2


def test_repeated_pairing_matched_in_order():
    data = {1: [{"winner": "A", "loser": "B"}, {"winner": "B", "loser": "A"}]}
    result = score_projections([_proj("A", "B", 0.5), _proj("A", "B", 0.5)], data)
    assert result["n"] == 2
    assert result["accuracy"] == 0.5


def test_empty_projections_have_defined_shape():
    assert score_projections([], DATA) == {
        "n": 0,
        "skipped": 0,
        "accuracy": None,
        "log_loss": None,
        "brier": None,
        "min_probability": None,
        "max_probability": None,
    }


def test_clamp_keeps_log_loss_finite_and_extremes_raw():
    result = score_projections([_proj("B", "A", 1.0)], DATA)
    assert math.isfinite(result["log_loss"])
    assert result["log_loss"] == pytest.approx(-math.log(1.0 - (1.0 - 1e-15)))
    assert result["max_probability"] == 1.0


def test_invalid_epsilon_rejected():
    with pytest.raises(ValueError):
        score_projections([], DATA, epsilon=0.0)


def test_scores_real_run_and_project():
    from keeks_elote import Backtest, create_arena

    data = {1: [{"winner": "A", "loser": "B"}], 2: [{"winner": "A", "loser": "B"}]}
    projections = Backtest(create_arena("elo")).run_and_project(data)
    result = score_projections(projections, data)
    assert result["n"] == 1
    assert result["accuracy"] == 1.0
