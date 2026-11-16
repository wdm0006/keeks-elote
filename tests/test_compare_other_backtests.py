"""compare_one_x_two_backtests / compare_portfolio_backtests drive the real engines with real BankRolls."""

import copy

import pytest
from keeks.bankroll import BankRoll

from keeks_elote import compare_one_x_two_backtests, compare_portfolio_backtests
from keeks_elote.multi_outcome_backtest import MultiOutcomeBacktest
from keeks_elote.portfolio_backtest import WeeklyPortfolioBacktest


class StubArena:
    def __init__(self, p=0.6):
        self.p = p

    def expected_score(self, a, b):
        return self.p

    def tournament(self, matchups):
        pass


class VectorStrategy:
    def __init__(self, fractions):
        self.fractions = tuple(fractions)

    def evaluate(self, probabilities, current_bankroll):
        return list(self.fractions)


class FixedWeights:
    def __init__(self, weights):
        self.weights = tuple(weights)

    def evaluate(self, current_bankroll):
        return self.weights


def bankroll():
    return BankRoll(initial_funds=1000.0, percent_bettable=1.0, max_transaction_loss=None)


def x2_game(home_score, away_score):
    return {
        "home": "C",
        "away": "D",
        "home_score": home_score,
        "away_score": away_score,
        "home_odds": 2.0,
        "draw_odds": 3.0,
        "away_odds": 4.0,
    }


X2_DATA = {0: [x2_game(1, 0)], 1: [x2_game(1, 0)], 2: [x2_game(0, 0)]}


def x2_factory(fractions):
    return lambda: (StubArena(), VectorStrategy(fractions), bankroll())


def x2_configs():
    return {"home": x2_factory((0.1, 0.0, 0.0)), "draw": x2_factory((0.0, 0.1, 0.0))}


def test_one_x_two_exact_rows_use_recorded_settlement():
    home, draw = compare_one_x_two_backtests(X2_DATA, x2_configs(), period_to_start_betting=0)

    # home: 100 at 2.0 wins (+100 -> 1100); 110 at 2.0 loses a draw (-110 -> 990)
    assert [r["stake"] for r in home["bet_history"]] == [100.0, 110.0]
    assert [r["won_leg"] for r in home["bet_history"]] == [0, 1]
    assert (home["opening_funds"], home["closing_funds"]) == (1000.0, 990.0)
    assert home["pnl"] == pytest.approx(-10.0)
    assert home["roi"] == pytest.approx(-10.0 / 210.0)
    # draw: 100 on the draw at 3.0 loses (-100 -> 900); 90 at 3.0 wins (+180 -> 1080)
    assert [r["stake"] for r in draw["bet_history"]] == [100.0, 90.0]
    assert draw["closing_funds"] == pytest.approx(1080.0)
    assert draw["pnl"] == pytest.approx(80.0)
    assert "summary" not in home


def test_one_x_two_alone_equals_in_company_and_inputs_unchanged():
    before = copy.deepcopy(X2_DATA)
    alone = compare_one_x_two_backtests(X2_DATA, {"draw": x2_factory((0.0, 0.1, 0.0))}, period_to_start_betting=0)[0]
    rows = compare_one_x_two_backtests(X2_DATA, x2_configs(), period_to_start_betting=0)
    assert rows[1] == alone
    assert X2_DATA == before


def test_one_x_two_factories_called_once_per_invocation():
    calls = []

    def build():
        calls.append(1)
        return x2_factory((0.1, 0.0, 0.0))()

    compare_one_x_two_backtests(X2_DATA, {"a": build, "b": build}, period_to_start_betting=0)
    assert len(calls) == 2


def test_one_x_two_options_reach_the_engine(monkeypatch):
    seen = []
    original = MultiOutcomeBacktest.run_explicit

    def spy(self, data, strategy, bankroll, **kwargs):
        seen.append((self._draw_rate, kwargs))
        return original(self, data, strategy, bankroll, **kwargs)

    monkeypatch.setattr(MultiOutcomeBacktest, "run_explicit", spy)
    compare_one_x_two_backtests(X2_DATA, {"a": x2_factory((0.1, 0.0, 0.0))})
    compare_one_x_two_backtests(
        X2_DATA,
        {"a": x2_factory((0.1, 0.0, 0.0))},
        draw_rate=0.3,
        seed=5,
        settlement="simulated",
        period_to_start_betting=0,
    )
    assert seen[0][1]["settlement"] == "recorded" and seen[0][0] == 0.25
    assert seen[1] == (0.3, {"period_to_start_betting": 0, "seed": 5, "settlement": "simulated"})


def test_one_x_two_failures_name_the_configuration():
    def boom():
        raise ValueError("nope")

    with pytest.raises(RuntimeError, match="'bad'") as info:
        compare_one_x_two_backtests(X2_DATA, {"bad": boom})
    assert isinstance(info.value.__cause__, ValueError)

    class Explode(VectorStrategy):
        def evaluate(self, probabilities, current_bankroll):
            raise RuntimeError("strategy exploded")

    # the engine ledgers per-game failures; a bad settlement mode raises out of the run
    with pytest.raises(RuntimeError, match="'run'") as info:
        compare_one_x_two_backtests(
            X2_DATA, {"run": x2_factory((0.1, 0.0, 0.0))}, settlement="bogus", period_to_start_betting=0
        )
    assert isinstance(info.value.__cause__, ValueError)


def test_one_x_two_reusing_collaborators_changes_the_second_row():
    """Mutation check: sharing the first run's bankroll leaks its state into the second row."""
    shared = bankroll()
    reused = {"first": lambda: (StubArena(), VectorStrategy((0.1, 0.0, 0.0)), shared)}
    reused["second"] = reused["first"]
    first, second = compare_one_x_two_backtests(X2_DATA, reused, period_to_start_betting=0)
    fresh = compare_one_x_two_backtests(X2_DATA, {"x": x2_factory((0.1, 0.0, 0.0))}, period_to_start_betting=0)[0]
    assert first["closing_funds"] == fresh["closing_funds"]
    assert second["opening_funds"] != fresh["opening_funds"]
    assert second["closing_funds"] != fresh["closing_funds"]


# --- weekly portfolio -------------------------------------------------------------------


def pf_game(winner, loser, ml=150):
    return {"winner": winner, "loser": loser, "winner_score": 21, "loser_score": 14, "winner_ml": ml}


PF_DATA = {1: [pf_game("A", "B")], 2: [pf_game("B", "C")], 3: [pf_game("C", "A")]}


def pf_factory(weight):
    return lambda: (StubArena(0.6), lambda model: FixedWeights([weight] * len(model.bets)), bankroll())


def pf_configs():
    return {"small": pf_factory(0.1), "big": pf_factory(0.5)}


def test_portfolio_rows_match_the_engine_ledger_exactly():
    rows = compare_portfolio_backtests(PF_DATA, pf_configs(), seed=11)

    for row, weight in zip(rows, (0.1, 0.5)):
        engine = WeeklyPortfolioBacktest(StubArena(0.6))
        br = bankroll()
        engine.run_explicit(PF_DATA, lambda model: FixedWeights([weight] * len(model.bets)), br, seed=11)
        assert row["bet_history"] == engine.bet_history
        assert row["opening_funds"] == 1000.0
        assert row["closing_funds"] == br.total_funds
        assert row["pnl"] == pytest.approx(sum(r["profit"] for r in engine.bet_history))
        assert "summary" not in row
    small, big = rows
    assert small["bet_history"][0]["stake"] == pytest.approx(100.0)
    assert big["bet_history"][0]["stake"] == pytest.approx(500.0)
    assert [r["name"] for r in rows] == ["small", "big"]
    assert small["closing_funds"] == pytest.approx(1000.0 + small["pnl"])


def test_portfolio_seeded_runs_reproduce_and_seeds_matter():
    a = compare_portfolio_backtests(PF_DATA, pf_configs(), seed=3)
    b = compare_portfolio_backtests(PF_DATA, pf_configs(), seed=3)
    assert a == b
    differing = [
        compare_portfolio_backtests(PF_DATA, pf_configs(), seed=s)[1]["bet_history"] != a[1]["bet_history"]
        for s in range(4, 24)
    ]
    assert any(differing)


def test_portfolio_alone_equals_in_company_and_inputs_unchanged():
    before = copy.deepcopy(PF_DATA)
    alone = compare_portfolio_backtests(PF_DATA, {"big": pf_factory(0.5)}, seed=3)[0]
    rows = compare_portfolio_backtests(PF_DATA, pf_configs(), seed=3)
    assert rows[1] == alone
    assert PF_DATA == before


def test_portfolio_factories_called_once_per_invocation():
    calls = []

    def build():
        calls.append(1)
        return pf_factory(0.1)()

    compare_portfolio_backtests(PF_DATA, {"a": build, "b": build}, seed=1)
    assert len(calls) == 2


def test_portfolio_failures_name_the_configuration():
    def boom():
        raise ValueError("nope")

    with pytest.raises(RuntimeError, match="'bad'") as info:
        compare_portfolio_backtests(PF_DATA, {"ok": pf_factory(0.1), "bad": boom})
    assert isinstance(info.value.__cause__, ValueError)

    with pytest.raises(RuntimeError, match="'run'") as info:
        compare_portfolio_backtests(
            PF_DATA, {"run": lambda: (StubArena(), lambda m: FixedWeights([0.1]), "not a bankroll")}
        )
    assert info.value.__cause__ is not None


def test_portfolio_reusing_collaborators_changes_the_second_row():
    """Mutation check: sharing the first run's bankroll leaks its state into the second row."""
    shared = bankroll()
    cfg = {"first": lambda: (StubArena(0.6), lambda m: FixedWeights([0.1] * len(m.bets)), shared)}
    cfg["second"] = cfg["first"]
    first, second = compare_portfolio_backtests(PF_DATA, cfg, seed=2)
    fresh = compare_portfolio_backtests(PF_DATA, {"x": pf_factory(0.1)}, seed=2)[0]
    assert first == {**fresh, "name": "first"}
    assert second["opening_funds"] != fresh["opening_funds"]
    assert second["closing_funds"] != fresh["closing_funds"]
