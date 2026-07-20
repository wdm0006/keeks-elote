import pytest
from keeks.bankroll import BankRoll

from keeks_elote import Backtest
from keeks_elote.backtest import american_to_decimal


class StubArena:
    def expected_score(self, winner, loser):
        return 0.75

    def tournament(self, matchups):
        pass


class FixedFractionStrategy:
    def __init__(self, selected_probability, fraction=0.2):
        self.selected_probability = selected_probability
        self.fraction = fraction

    def evaluate(self, probability, current_bankroll):
        return self.fraction if probability == self.selected_probability else 0.0


def run_single_bet(selected_probability):
    data = {
        1: [],
        2: [{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": -200}],
    }
    bankroll = BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)

    return Backtest(StubArena()).run_explicit(
        data,
        FixedFractionStrategy(selected_probability),
        bankroll,
        period_to_start_betting=1,
    )


def test_winning_bet_returns_stake_and_payoff():
    bankroll = run_single_bet(selected_probability=0.75)

    assert bankroll.total_funds == 1150.0


def test_losing_bet_deducts_stake():
    bankroll = run_single_bet(selected_probability=0.25)

    assert bankroll.total_funds == 900.0


@pytest.mark.parametrize(("american_odds", "decimal_odds"), [(150, 2.5), (-200, 1.5)])
def test_american_to_decimal(american_odds, decimal_odds):
    assert american_to_decimal(american_odds) == decimal_odds
