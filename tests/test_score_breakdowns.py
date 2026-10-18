import math

import pytest

from keeks_elote import calibration_table, score_projections, score_projections_by_period

DATA = {
    1: [{"winner": "A", "loser": "B"}, {"winner": "C", "loser": "D"}],
    2: [{"winner": "E", "loser": "F"}, {"winner": "G", "loser": "H"}],
    3: [{"winner": "I", "loser": "J"}],
}


def _proj(winner, loser, probability, period):
    return {"period": period, "predicted_winner": winner, "predicted_loser": loser, "probability": probability}


PROJECTIONS = [
    _proj("A", "B", 0.8, 1),  # hit
    _proj("D", "C", 0.6, 1),  # miss
    _proj("E", "F", 0.95, 2),  # hit
    _proj("X", "Y", 0.7, 2),  # unmatched
    _proj("Q", "R", 0.9, 4),  # period with only skipped projections
]


def test_by_period_exact_values():
    result = score_projections_by_period(PROJECTIONS, DATA)
    assert list(result) == [1, 2, 4]
    assert result[1]["n"] == 2
    assert result[1]["skipped"] == 0
    assert result[1]["accuracy"] == 0.5
    assert result[1]["log_loss"] == pytest.approx(-(math.log(0.8) + math.log(0.4)) / 2)
    assert result[1]["brier"] == pytest.approx(0.2)
    assert result[2]["n"] == 1
    assert result[2]["skipped"] == 1
    assert result[2]["accuracy"] == 1.0
    assert result[2]["log_loss"] == pytest.approx(-math.log(0.95))
    assert result[2]["brier"] == pytest.approx(0.05**2)
    assert result[4] == {"n": 0, "skipped": 1, "accuracy": None, "log_loss": None, "brier": None}


def test_by_period_agrees_with_aggregate():
    aggregate = score_projections(PROJECTIONS, DATA)
    by_period = score_projections_by_period(PROJECTIONS, DATA)
    assert sum(row["n"] for row in by_period.values()) == aggregate["n"] == 3
    assert sum(row["skipped"] for row in by_period.values()) == aggregate["skipped"] == 2


def test_calibration_table_exact_values():
    table = calibration_table(PROJECTIONS, DATA, bins=5)
    assert [(row["lo"], row["hi"]) for row in table] == [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
    assert [row["n"] for row in table] == [0, 0, 0, 1, 2]
    assert table[0]["mean_predicted"] is None and table[0]["observed_rate"] is None
    assert table[3]["mean_predicted"] == 0.6 and table[3]["observed_rate"] == 0.0
    assert table[4]["mean_predicted"] == pytest.approx((0.8 + 0.95) / 2)
    assert table[4]["observed_rate"] == 1.0


def test_calibration_table_skips_unmatched_and_includes_probability_one():
    table = calibration_table([_proj("A", "B", 1.0, 1), _proj("X", "Y", 0.7, 1)], DATA, bins=10)
    assert len(table) == 10
    assert sum(row["n"] for row in table) == 1
    assert table[9]["n"] == 1 and table[9]["observed_rate"] == 1.0


@pytest.mark.parametrize("bins", [0, -1, 2.5, True, "10", None])
def test_calibration_table_rejects_bad_bins(bins):
    with pytest.raises(ValueError, match="bins"):
        calibration_table(PROJECTIONS, DATA, bins=bins)


def test_by_period_rejects_bad_epsilon():
    with pytest.raises(ValueError, match="epsilon"):
        score_projections_by_period(PROJECTIONS, DATA, epsilon=0.0)
