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


def test_overdrawn_bet_is_capped_rather_than_dropped(caplog):
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

    # Every selected bet reaches bet() and is accepted; the third is clamped to the
    # live bettable funds rather than being rejected and silently dropped.
    assert bankroll.bet_amounts == [400.0, 400.0, 200.0]
    assert bankroll.settled_amounts == [400.0, 400.0, 200.0]
    assert bankroll.total_funds == 0.0

    capped_warnings = [
        record.message
        for record in caplog.records
        if record.levelno == logging.WARNING and "exceeds bettable funds" in record.message
    ]
    assert len(capped_warnings) == 1
    assert "on F" in capped_warnings[0]


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
