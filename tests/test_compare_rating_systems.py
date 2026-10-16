import math

import pytest

import keeks_elote.model_evaluation as me
from keeks_elote import Backtest, compare_rating_systems, create_arena, score_projections

DATA = {
    1: [{"winner": "A", "loser": "B"}, {"winner": "C", "loser": "D"}],
    2: [{"winner": "A", "loser": "C"}, {"winner": "D", "loser": "B"}],
    3: [{"winner": "B", "loser": "A"}, {"winner": "C", "loser": "D"}],
}
KEYS = {"system", "n", "skipped", "accuracy", "log_loss", "brier", "min_probability", "max_probability"}


def _alone(name):
    projections = Backtest(create_arena(name)).run_and_project(DATA)
    return {"system": name, **score_projections(projections, DATA)}


def test_rows_match_independent_runs_regardless_of_order():
    # Glicko's deviation decay reads the wall clock, so compare with a tolerance.
    names = ["elo", "glicko", "trueskill"]
    rows = {r["system"]: r for r in compare_rating_systems(DATA, names)}
    reordered = {r["system"]: r for r in compare_rating_systems(DATA, names[::-1])}
    for name in names:
        assert set(rows[name]) == KEYS
        assert rows[name] == pytest.approx(_alone(name), rel=1e-6)
        assert reordered[name] == pytest.approx(rows[name], rel=1e-6)


def test_exact_values_for_elo_on_fixture():
    (row,) = compare_rating_systems(DATA, ["elo"])
    p = 0.5910755963149434
    assert row["system"] == "elo"
    assert row["n"] == 4
    assert row["skipped"] == 0
    assert row["accuracy"] == 0.0
    assert row["log_loss"] == pytest.approx(-(3 * math.log(0.5) + math.log(1 - p)) / 4)
    assert row["brier"] == pytest.approx((3 * 0.25 + p**2) / 4)
    assert row["min_probability"] == 0.5
    assert row["max_probability"] == pytest.approx(p)


def test_default_is_all_systems_sorted_by_log_loss():
    rows = compare_rating_systems(DATA)
    assert {r["system"] for r in rows} == set(me.RATING_SYSTEMS)
    losses = [r["log_loss"] for r in rows if "error" not in r and r["log_loss"] is not None]
    assert losses == sorted(losses)


def test_unknown_name_raises_before_any_run(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ran")

    monkeypatch.setattr(me, "create_arena", boom)
    with pytest.raises(ValueError, match="nope"):
        compare_rating_systems(DATA, ["elo", "nope"])
    with pytest.raises(ValueError, match="bogus"):
        compare_rating_systems(DATA, ["elo"], {"bogus": {}})


def test_failing_system_yields_error_row_and_others_score(monkeypatch):
    real = me.create_arena

    def flaky(name, **kw):
        if name == "glicko":
            raise RuntimeError("kaboom")
        return real(name, **kw)

    monkeypatch.setattr(me, "create_arena", flaky)
    rows = compare_rating_systems(DATA, ["glicko", "elo"])
    assert rows[0] == _alone("elo")
    assert rows[1] == {"system": "glicko", "error": "RuntimeError: kaboom"}


def test_none_log_loss_sorts_after_scored_and_before_errors(monkeypatch):
    real = me.create_arena

    def fake(name, **kw):
        if name == "colley":
            raise ValueError("x")
        return real(name, **kw)

    monkeypatch.setattr(me, "create_arena", fake)
    empty = {1: [{"winner": "A", "loser": "B"}]}
    rows = compare_rating_systems(empty, ["colley", "elo"])
    assert [r["system"] for r in rows] == ["elo", "colley"]
    assert rows[0]["log_loss"] is None and rows[0]["n"] == 0
    assert "error" in rows[1]
    scored = compare_rating_systems(DATA, ["colley", "elo", "glicko"])
    assert [r["system"] for r in scored][-1] == "colley"
    assert all(r["log_loss"] is not None for r in scored[:2])
