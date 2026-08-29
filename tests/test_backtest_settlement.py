import logging

import pytest
from keeks.bankroll import BankRoll
from keeks.binary_strategies import KellyCriterion

from keeks_elote import Backtest
from keeks_elote.backtest import american_to_decimal


class StubArena:
    def expected_score(self, winner, loser):
        return 0.75

    def tournament(self, matchups):
        pass


class RecordingArena(StubArena):
    def __init__(self):
        self.matchups = []

    def tournament(self, matchups):
        self.matchups.extend(matchups)


class ProbabilityArena(StubArena):
    def __init__(self, probability):
        self.probability = probability

    def expected_score(self, winner, loser):
        return self.probability


class FixedFractionStrategy:
    def __init__(self, selected_probability, fraction=0.2):
        self.selected_probability = selected_probability
        self.fraction = fraction

    def evaluate(self, probability, current_bankroll):
        return self.fraction if probability == self.selected_probability else 0.0


class FixedFractionForAllBetsStrategy:
    def __init__(self, fraction=0.2):
        self.fraction = fraction

    def evaluate(self, probability, current_bankroll):
        return self.fraction


class RecordingBankRoll(BankRoll):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bet_amounts = []
        self.settled_amounts = []

    def bet(self, amount):
        self.bet_amounts.append(amount)
        result = super().bet(amount)
        self.settled_amounts.append(amount)
        return result


def run_single_bet(selected_probability, bankroll=None):
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    if bankroll is None:
        bankroll = BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    return Backtest(StubArena()).run_explicit(
        data,
        FixedFractionStrategy(selected_probability),
        bankroll,
        period_to_start_betting=1,
    )


def test_winning_bet_returns_stake_and_payoff():
    bankroll = run_single_bet(selected_probability=0.75)

    assert bankroll.total_funds == 1300.0


def test_losing_bet_deducts_stake():
    bankroll = run_single_bet(selected_probability=0.25)

    assert bankroll.total_funds == 800.0


def test_stake_uses_the_bankroll_the_strategy_was_quoted():
    """The strategy prices its fraction against total funds, so that is the staking base."""
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    run_single_bet(selected_probability=0.75, bankroll=bankroll)

    assert bankroll.bet_amounts == [200.0]


def test_overdrawn_period_is_scaled_proportionally_not_dropped(caplog):
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "C", "loser": "D", "winner_odds": 150, "loser_odds": -200},
            {"winner": "E", "loser": "F", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=1.0, max_draw_down=1.0)

    with caplog.at_level(logging.WARNING):
        Backtest(StubArena()).run_explicit(
            data,
            FixedFractionStrategy(0.25, fraction=0.4),
            bankroll,
            period_to_start_betting=1,
        )

    # Three bets at 0.4 request 120% of the bankroll against a 100% budget, so every
    # stake is scaled by the same factor. Each bet still reaches bet() rather than
    # being rejected, and the earliest games no longer consume the whole bankroll.
    # The final cent of difference is the residual per-bet clamp against
    # bettable_funds, which BankRoll rounds to two places.
    assert bankroll.bet_amounts == [pytest.approx(1000.0 / 3, abs=0.01)] * 3
    assert bankroll.settled_amounts == [pytest.approx(1000.0 / 3, abs=0.01)] * 3
    assert bankroll.total_funds == pytest.approx(0.0, abs=0.01)

    capped_warnings = [
        record.message
        for record in caplog.records
        if record.levelno == logging.WARNING and "scaling every stake" in record.message
    ]
    assert len(capped_warnings) == 1
    assert "120.0% of the bankroll" in capped_warnings[0]


def test_same_period_bets_use_opening_bankroll():
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    Backtest(StubArena()).run_explicit(
        data,
        FixedFractionForAllBetsStrategy(),
        bankroll,
        period_to_start_betting=1,
    )

    assert bankroll.bet_amounts == [200.0, 200.0]
    assert bankroll.total_funds == 1100.0


def run_kelly_bet(winner_odds, *, price_bets_at_true_odds=True):
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": winner_odds, "loser_odds": -500}],
    }
    strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)
    bankroll = BankRoll(initial_funds=1000.0, percent_bettable=1.0, max_draw_down=1.0)

    result = Backtest(ProbabilityArena(0.55)).run_explicit(
        data,
        strategy,
        bankroll,
        period_to_start_betting=1,
        price_bets_at_true_odds=price_bets_at_true_odds,
    )
    return result, strategy


def test_heavy_favorite_price_prevents_negative_expected_value_bet():
    bankroll, strategy = run_kelly_bet(-500)

    assert bankroll.total_funds == 1000.0
    assert strategy.payoff == 1.0
    assert strategy.loss == 1.0


def test_plus_money_price_sizes_bet_larger_than_even_money():
    plus_money_bankroll, _ = run_kelly_bet(150)
    even_money_bankroll, _ = run_kelly_bet(100)

    assert plus_money_bankroll.total_funds == 1375.0
    assert even_money_bankroll.total_funds == 1100.0


def test_true_odds_pricing_can_be_disabled():
    bankroll, strategy = run_kelly_bet(-500, price_bets_at_true_odds=False)

    assert bankroll.total_funds == 1020.0
    assert strategy.payoff == 1.0


@pytest.mark.parametrize(("american_odds", "decimal_odds"), [(150, 2.5), (-200, 1.5), (100.0, 2.0), (-100.0, 2.0)])
def test_american_to_decimal(american_odds, decimal_odds):
    assert american_to_decimal(american_odds) == decimal_odds


@pytest.mark.parametrize("american_odds", [0, 0.0, -0.0, float("inf"), float("-inf"), float("nan")])
def test_american_to_decimal_rejects_zero_and_non_finite_odds(american_odds):
    with pytest.raises(ValueError):
        american_to_decimal(american_odds)


@pytest.mark.parametrize("american_odds", [True, False, "150", "-200", [150], complex(150, 0)])
def test_american_to_decimal_rejects_non_real_odds(american_odds):
    with pytest.raises(TypeError):
        american_to_decimal(american_odds)


def test_invalid_odds_skip_only_that_side(caplog):
    """One unusable price must not cost the game its opposite wager or its rating update."""
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": float("nan")}],
    }
    arena = RecordingArena()
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    with caplog.at_level(logging.WARNING):
        Backtest(arena).run_explicit(
            data,
            FixedFractionForAllBetsStrategy(),
            bankroll,
            period_to_start_betting=1,
        )

    # The strategy stakes every side it is offered, so only the invalid price is missing:
    # A is staked 200.0 at +150 and settles as a winner.
    assert bankroll.bet_amounts == [200.0]
    assert bankroll.total_funds == 1300.0
    assert ("A", "B") in arena.matchups

    invalid_odds_warnings = [
        record.message
        for record in caplog.records
        if record.levelno == logging.WARNING and "invalid odds" in record.message
    ]
    assert len(invalid_odds_warnings) == 1
    assert "on B" in invalid_odds_warnings[0]
    assert "nan" in invalid_odds_warnings[0]


def test_period_exposure_never_exceeds_the_bettable_budget():
    """percent_bettable caps the period's total stake, not each bet in isolation.

    A strategy quoting a fraction per game cannot know how many other games it is
    being asked about, so a confident week routinely requests several times the
    bankroll. Clamping each bet against the live funds lets the earliest games spend
    everything; scaling the period keeps the total inside the budget.
    """
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "C", "loser": "D", "winner_odds": 150, "loser_odds": -200},
            {"winner": "E", "loser": "F", "winner_odds": 150, "loser_odds": -200},
            {"winner": "G", "loser": "H", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    Backtest(StubArena()).run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.4),
        bankroll,
        period_to_start_betting=1,
    )

    # Four bets at 0.4 request 1600 against a budget of 500.
    assert sum(bankroll.bet_amounts) == pytest.approx(500.0)
    # Proportional scaling, so equal requests stay equal.
    assert bankroll.bet_amounts == [pytest.approx(125.0)] * 4


def test_equal_fractions_stay_equal_after_scaling():
    """Scaling must not advantage whichever game happens to be settled first."""
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "C", "loser": "D", "winner_odds": 150, "loser_odds": -200},
            {"winner": "E", "loser": "F", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    bankroll = RecordingBankRoll(initial_funds=1000.0, percent_bettable=0.6, max_draw_down=1.0)

    Backtest(StubArena()).run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.5),
        bankroll,
        period_to_start_betting=1,
    )

    assert len({round(a, 6) for a in bankroll.bet_amounts}) == 1
    assert sum(bankroll.bet_amounts) == pytest.approx(600.0)


def test_scores_are_forwarded_to_the_arena_when_present():
    """Margin-aware systems need the scores, not just who won."""
    arena = RecordingArena()
    data = {
        1: [{"winner": "A", "loser": "B", "winner_score": 31, "loser_score": 17}],
    }
    Backtest(arena).run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.1),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    assert arena.matchups == [("A", "B", None, None, 1.0, (31.0, 17.0))]


def test_a_game_without_scores_keeps_the_plain_form():
    """Win/loss systems must keep receiving two-element tuples."""
    arena = RecordingArena()
    data = {1: [{"winner": "A", "loser": "B"}]}
    Backtest(arena).run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.1),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    assert arena.matchups == [("A", "B")]


def test_unparseable_scores_fall_back_to_the_plain_form(caplog):
    """A malformed score must not take down the rating update."""
    arena = RecordingArena()
    data = {1: [{"winner": "A", "loser": "B", "winner_score": "n/a", "loser_score": 17}]}
    with caplog.at_level(logging.WARNING):
        Backtest(arena).run_explicit(
            data,
            FixedFractionStrategy(0.25, fraction=0.1),
            BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
            period_to_start_betting=1,
        )

    assert arena.matchups == [("A", "B")]
    assert any("unparseable scores" in record.message for record in caplog.records)


def test_scores_that_contradict_the_result_fall_back_to_the_plain_form(caplog):
    """A 0-0 placeholder must not be fed through as a real tie margin."""
    arena = RecordingArena()
    data = {1: [{"winner": "A", "loser": "B", "winner_score": 0, "loser_score": 0}]}
    with caplog.at_level(logging.WARNING):
        Backtest(arena).run_explicit(
            data,
            FixedFractionStrategy(0.25, fraction=0.1),
            BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
            period_to_start_betting=1,
        )

    assert arena.matchups == [("A", "B")]
    assert any("do not show" in record.message for record in caplog.records)


def test_bet_history_is_empty_before_the_first_run():
    assert Backtest(StubArena()).bet_history == []


def test_bet_history_is_cleared_not_appended_on_a_second_run():
    """The Backtest instance is reusable, so a second run must not carry the first."""
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    backtest = Backtest(StubArena())

    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.75),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )
    assert len(backtest.bet_history) == 1

    backtest.run_explicit(
        data,
        FixedFractionForAllBetsStrategy(),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    # Two bets this run, not three accumulated across both.
    assert len(backtest.bet_history) == 2
    assert [record["label"] for record in backtest.bet_history] == ["A", "B"]


def test_bet_history_records_a_winning_bet_exactly():
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.75),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    # The same 1300.0 balance test_winning_bet_returns_stake_and_payoff pins, decomposed:
    # 200.0 staked on A at +150 (payoff 1.5) returns 300.0 of profit.
    assert backtest.bet_history == [
        {
            "period": 2,
            "label": "A",
            "opponent": "B",
            "fraction": 0.2,
            "stake": 200.0,
            "payoff": 1.5,
            "won": True,
            "profit": 300.0,
            "bankroll_after": 1300.0,
            "skipped_zero_stake": False,
            "error": None,
        }
    ]


def test_bet_history_records_a_losing_bet_exactly():
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.25),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    record = backtest.bet_history[0]
    assert record["label"] == "B"
    assert record["stake"] == 200.0
    assert record["payoff"] == 0.5
    assert record["won"] is False
    assert record["profit"] == -200.0
    assert record["bankroll_after"] == 800.0


def test_bet_history_records_the_bankroll_trajectory_across_a_period():
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    backtest.run_explicit(
        data,
        FixedFractionForAllBetsStrategy(),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    assert [record["bankroll_after"] for record in backtest.bet_history] == [1300.0, 1100.0]


def test_bet_history_records_scaled_stakes_not_requested_ones():
    """The recorded stake is what reached bet(), after the period's exposure scaling.

    Four bets at 0.4 request 400.0 each against a budget of 500.0, so a record derived
    from ``opening_funds * fraction`` would say 400.0 and the sum would be 1600.0.
    """
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "C", "loser": "D", "winner_odds": 150, "loser_odds": -200},
            {"winner": "E", "loser": "F", "winner_odds": 150, "loser_odds": -200},
            {"winner": "G", "loser": "H", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.4),
        BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    stakes = [record["stake"] for record in backtest.bet_history]
    assert stakes == [125.0] * 4
    assert sum(stakes) == pytest.approx(500.0)
    assert [record["profit"] for record in backtest.bet_history] == [-125.0] * 4


def test_bet_history_records_the_clamped_amount():
    """The last bet of an over-committed period is clamped down to the live funds."""
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [
            {"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200},
            {"winner": "C", "loser": "D", "winner_odds": 150, "loser_odds": -200},
            {"winner": "E", "loser": "F", "winner_odds": 150, "loser_odds": -200},
        ],
    }
    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.25, fraction=0.4),
        BankRoll(initial_funds=1000.0, percent_bettable=1.0, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    stakes = [record["stake"] for record in backtest.bet_history]
    # Scaling gives 1000/3 each; by the third bet the bank is down to 333.33 (BankRoll
    # rounds to two places), so the residual clamp trims that final stake.
    assert stakes[:2] == [pytest.approx(1000.0 / 3)] * 2
    assert stakes[2] == 333.33
    assert stakes[2] < stakes[0]
    assert backtest.bet_history[2]["profit"] == -333.33
    assert backtest.bet_history[2]["bankroll_after"] == 0.0


def test_bet_history_records_a_zero_stake_bet_with_its_flag():
    """A candidate scaled to nothing is recorded, not silently dropped."""
    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    bankroll = BankRoll(initial_funds=1000.0, percent_bettable=0.0, max_draw_down=1.0)

    result = backtest.run_explicit(
        data,
        FixedFractionStrategy(0.75),
        bankroll,
        period_to_start_betting=1,
    )

    assert result is bankroll
    assert result.total_funds == 1000.0
    record = backtest.bet_history[0]
    assert record["label"] == "A"
    assert record["fraction"] == 0.2
    assert record["stake"] == 0.0
    assert record["profit"] == 0.0
    assert record["skipped_zero_stake"] is True
    assert record["error"] is None


def test_bet_history_records_a_failed_settlement_with_its_error():
    """A settlement that raises is accounted for rather than vanishing from the record."""

    class FailingBankRoll(BankRoll):
        def bet(self, amount):
            raise RuntimeError("bookmaker unavailable")

    backtest = Backtest(StubArena())
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    backtest.run_explicit(
        data,
        FixedFractionStrategy(0.75),
        FailingBankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0),
        period_to_start_betting=1,
    )

    record = backtest.bet_history[0]
    assert record["stake"] == 0.0
    assert record["profit"] == 0.0
    assert record["skipped_zero_stake"] is False
    assert record["error"] == "bookmaker unavailable"
    assert record["bankroll_after"] == 1000.0
