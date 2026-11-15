"""compare_backtests drives the real Backtest with real BankRoll objects and hand-computed values."""

import copy

import pytest
from keeks.bankroll import BankRoll

import keeks_elote.comparison as comparison_module
from keeks_elote import Backtest, compare_backtests, roi


class FavouriteArena:
    """Prices "A" at 0.75 on whichever side it appears and everyone else at 0.25."""

    def expected_score(self, a, b):
        return 0.75 if a == "A" else 0.25

    def tournament(self, matchups):
        pass


class FractionOnA:
    def __init__(self, fraction):
        self.fraction = fraction

    def evaluate(self, probability, current_bankroll):
        return self.fraction if probability == 0.75 else 0.0


def bankroll(percent_bettable=1.0):
    return BankRoll(initial_funds=1000.0, percent_bettable=percent_bettable, max_transaction_loss=1.0)


def factory(fraction, percent_bettable=1.0):
    return lambda: (FavouriteArena(), FractionOnA(fraction), bankroll(percent_bettable))


# Period 2: A wins at +150 (payoff 1.5). Period 3: A loses at -200 (payoff 0.5). Period 4: A wins at +100.
SCHEDULE = {
    1: [],
    2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    3: [{"winner": "B", "loser": "A", "winner_odds": 150, "loser_odds": -200}],
    4: [{"winner": "A", "loser": "C", "winner_odds": 100, "loser_odds": 100}],
}


def configs():
    return {"small": factory(0.1), "big": factory(0.5)}


def test_exact_ledgers_balances_pnl_roi_and_summary():
    small, big = compare_backtests(SCHEDULE, configs(), period_to_start_betting=1)

    # small: 100 -> 1150; 115 loses -> 1035; 103.5 at payoff 1.0 -> 1138.5
    assert [row["name"] for row in (small, big)] == ["small", "big"]
    assert [r["stake"] for r in small["bet_history"]] == [100.0, 115.0, 103.5]
    assert [r["bankroll_after"] for r in small["bet_history"]] == [1150.0, 1035.0, 1138.5]
    assert (small["opening_funds"], small["closing_funds"]) == (1000.0, 1138.5)
    assert small["pnl"] == pytest.approx(138.5)
    assert small["roi"] == pytest.approx(138.5 / 318.5)
    assert small["summary"]["placed_bets"] == 3
    assert (small["summary"]["wins"], small["summary"]["losses"]) == (2, 1)
    assert small["summary"]["net_profit"] == pytest.approx(138.5)

    # big: 500 -> 1750; 875 loses -> 875; 437.5 -> 1312.5
    assert [r["stake"] for r in big["bet_history"]] == [500.0, 875.0, 437.5]
    assert [r["profit"] for r in big["bet_history"]] == [750.0, -875.0, 437.5]
    assert big["closing_funds"] == 1312.5
    assert big["pnl"] == pytest.approx(312.5)
    assert big["roi"] == pytest.approx(312.5 / 1812.5)
    assert [r["period"] for r in big["bet_history"]] == [2, 3, 4]


def test_reported_stakes_are_after_exposure_scaling():
    """Two bets at fraction 0.4 with percent_bettable 0.5 scale 400 each down to 250."""
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "A", "loser": "C", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    (row,) = compare_backtests(data, {"capped": factory(0.4, percent_bettable=0.5)}, period_to_start_betting=1)

    assert [r["stake"] for r in row["bet_history"]] == [250.0, 250.0]
    assert row["closing_funds"] == 1750.0
    assert row["pnl"] == 750.0
    assert row["roi"] == 1.5


def test_values_do_not_depend_on_order_or_company():
    alone = compare_backtests(SCHEDULE, {"big": factory(0.5)}, period_to_start_betting=1)[0]
    first, second = compare_backtests(SCHEDULE, {"big": factory(0.5), "small": factory(0.1)}, period_to_start_betting=1)
    reversed_ = compare_backtests(SCHEDULE, {"small": factory(0.1), "big": factory(0.5)}, period_to_start_betting=1)

    assert first == alone
    assert reversed_[1] == alone
    assert reversed_[0] == second


def test_factories_called_once_and_repeat_calls_start_fresh():
    calls = []

    def counted(fraction):
        def build():
            calls.append(fraction)
            return factory(fraction)()

        return build

    cfgs = {"a": counted(0.1), "b": counted(0.5)}
    first = compare_backtests(SCHEDULE, cfgs, period_to_start_betting=1)
    second = compare_backtests(SCHEDULE, cfgs, period_to_start_betting=1)

    assert calls == [0.1, 0.5, 0.1, 0.5]
    assert first == second
    assert first[0]["bet_history"] is not second[0]["bet_history"]


def test_input_schedule_is_unchanged():
    before = copy.deepcopy(SCHEDULE)
    compare_backtests(SCHEDULE, configs(), period_to_start_betting=1)
    assert SCHEDULE == before


def test_empty_configurations_return_empty_list():
    assert compare_backtests(SCHEDULE, {}) == []


def test_options_reach_run_explicit(monkeypatch):
    seen = []
    original = Backtest.run_explicit

    def spy(self, data, strategy, bankroll, period_to_start_betting=3, price_bets_at_true_odds=True):
        seen.append((period_to_start_betting, price_bets_at_true_odds))
        return original(self, data, strategy, bankroll, period_to_start_betting, price_bets_at_true_odds)

    monkeypatch.setattr(Backtest, "run_explicit", spy)
    compare_backtests(SCHEDULE, configs())
    compare_backtests(SCHEDULE, configs(), period_to_start_betting=1, price_bets_at_true_odds=False)

    assert seen == [(3, True)] * 2 + [(1, False)] * 2


def test_sparse_out_of_order_periods_and_warmup_through_real_engine():
    data = {
        9: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
        1: [],
        5: [{"winner": "B", "loser": "A", "winner_odds": 150, "loser_odds": -200}],
    }
    (betting,) = compare_backtests(data, {"x": factory(0.1)}, period_to_start_betting=2)
    # Period 5: A loses 100 at payoff 0.5 -> 900. Period 9: 90 at +150 -> 1035.
    assert [(r["period"], r["stake"]) for r in betting["bet_history"]] == [(5, 100.0), (9, 90.0)]
    assert betting["closing_funds"] == 1035.0

    (warmup,) = compare_backtests(data, {"x": factory(0.1)}, period_to_start_betting=5)
    # Period 5 is still warm-up, so only period 9 settles: 100 at +150 -> 1150.
    assert [(r["period"], r["stake"]) for r in warmup["bet_history"]] == [(9, 100.0)]
    assert warmup["closing_funds"] == 1150.0


def test_factory_failure_names_configuration_and_keeps_cause():
    def broken():
        raise ValueError("no arena today")

    with pytest.raises(RuntimeError, match="'broken'") as info:
        compare_backtests(SCHEDULE, {"ok": factory(0.1), "broken": broken})
    assert isinstance(info.value.__cause__, ValueError)


def test_run_failure_names_configuration_and_keeps_cause():
    class ExplodingArena(FavouriteArena):
        def tournament(self, matchups):
            raise KeyError("rating store gone")

    cfgs = {"boom": lambda: (ExplodingArena(), FractionOnA(0.1), bankroll())}
    with pytest.raises(RuntimeError, match="'boom'") as info:
        compare_backtests(SCHEDULE, cfgs, period_to_start_betting=1)
    assert isinstance(info.value.__cause__, KeyError)


def test_invalid_configurations_rejected_before_any_factory_runs():
    called = []
    with pytest.raises(TypeError, match="'bad'"):
        compare_backtests(SCHEDULE, {"ok": lambda: called.append(1), "bad": 3})
    assert called == []
    with pytest.raises(TypeError, match="mapping"):
        compare_backtests(SCHEDULE, [factory(0.1)])
    with pytest.raises(TypeError, match="'short'"):
        compare_backtests(SCHEDULE, {"short": lambda: (FavouriteArena(), FractionOnA(0.1))})


def test_per_candidate_failures_stay_visible_in_the_summary():
    class FailsOnSecondEvaluation:
        calls = []

        def evaluate(self, probability, current_bankroll):
            self.calls.append(probability)
            if len(self.calls) == 2:
                raise RuntimeError("cannot price")
            return 0.1 if probability == 0.75 else 0.0

    cfgs = {"flaky": lambda: (FavouriteArena(), FailsOnSecondEvaluation(), bankroll())}
    (row,) = compare_backtests(SCHEDULE, cfgs, period_to_start_betting=1)

    assert row["summary"]["failed_bets"] == 1
    assert any("cannot price" in reason for reason in row["summary"]["failure_reasons"])
    assert row["summary"]["placed_bets"] == 3  # the failed candidate was the other side of a game
    assert [r["error"] is not None for r in row["bet_history"]].count(True) == 1


def test_zero_stake_roi_matches_the_roi_helper():
    (row,) = compare_backtests(SCHEDULE, {"none": factory(0.5, percent_bettable=0.0)}, period_to_start_betting=1)
    assert row["roi"] == roi(row["bet_history"]) == 0.0
    assert row["closing_funds"] == row["opening_funds"] == 1000.0
    assert row["summary"]["skipped_zero_stake"] == 3


def test_factories_returning_shared_state_are_the_callers_problem():
    """Documented contract: a shared bankroll contaminates later rows (not copied by the helper)."""
    shared = bankroll()
    cfgs = {n: (lambda: (FavouriteArena(), FractionOnA(0.1), shared)) for n in ("one", "two")}
    one, two = compare_backtests(SCHEDULE, cfgs, period_to_start_betting=1)
    assert two["opening_funds"] == one["closing_funds"]
    assert comparison_module.compare_backtests is compare_backtests
