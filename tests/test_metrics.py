"""Tests for the value-metrics surface: ``edge``, ``to_decimal``, ``pnl``, and ``roi``.

Golden values pin the math (the expected value per unit staked, the either-format
detection rule), known ledgers pin the ledger metrics, and stubbed backtest runs
pin the wiring: decimal odds must price bets exactly where American odds always
have, side by side with them.
"""

import logging

import pytest
from keeks.bankroll import BankRoll

from keeks_elote import Backtest, american_to_decimal, edge, pnl, roi, summarize_bet_history, to_decimal
from keeks_elote.backtest import _decimal_odds_for_side


class StubArena:
    """Always favors the listed winner at a fixed probability."""

    def expected_score(self, winner, loser):
        return 0.75

    def tournament(self, matchups):
        pass


class FixedFractionForAllBetsStrategy:
    """Quotes the same stake fraction for every candidate."""

    def __init__(self, fraction=0.1):
        self.fraction = fraction

    def evaluate(self, probability, current_bankroll):
        return self.fraction


# A known ledger: two wins (90, 25) and one loss (-100) over 250 staked, with the
# full record schema run_explicit documents.
def _record(stake, profit, **overrides):
    record = {
        "period": 2,
        "label": "A",
        "opponent": "B",
        "fraction": 0.1,
        "stake": stake,
        "payoff": 1.0,
        "won": profit > 0,
        "profit": profit,
        "bankroll_after": 1000.0,
        "skipped_zero_stake": False,
        "error": None,
    }
    record.update(overrides)
    return record


LEDGER = [
    _record(100.0, 90.0),
    _record(100.0, -100.0),
    _record(50.0, 25.0),
]


class TestEdge:
    def test_golden_even_money_value(self):
        assert edge(0.5, 2.1) == pytest.approx(0.05)

    def test_zero_exactly_at_break_even(self):
        assert edge(0.5, 2.0) == 0.0
        assert edge(0.25, 4.0) == 0.0

    def test_negative_when_price_beats_probability(self):
        # p*d = 0.8 < 1: a 40% chance at even money loses a fifth of a unit per bet.
        assert edge(0.4, 2.0) == pytest.approx(-0.2)

    def test_extremes(self):
        assert edge(0.0, 2.0) == -1.0
        assert edge(1.0, 2.0) == 1.0

    def test_matches_the_closed_form(self):
        for probability, odds in [(0.3, 3.4), (0.6, 1.8), (0.55, 2.05)]:
            assert edge(probability, odds) == pytest.approx(probability * odds - 1)

    @pytest.mark.parametrize("probability", [-0.1, 1.1])
    def test_rejects_probability_outside_unit_interval(self, probability):
        with pytest.raises(ValueError):
            edge(probability, 2.0)

    @pytest.mark.parametrize("odds", [0.5, 0.999])
    def test_rejects_sub_one_decimal_odds(self, odds):
        with pytest.raises(ValueError):
            edge(0.5, odds)

    @pytest.mark.parametrize("probability,odds", [("0.5", 2.0), (True, 2.0), (0.5, "2.0"), (0.5, True)])
    def test_rejects_non_real_arguments(self, probability, odds):
        with pytest.raises(TypeError):
            edge(probability, odds)

    @pytest.mark.parametrize(
        "probability,odds",
        [(float("nan"), 2.0), (float("inf"), 2.0), (0.5, float("nan")), (0.5, float("inf"))],
    )
    def test_rejects_non_finite_arguments(self, probability, odds):
        with pytest.raises(ValueError):
            edge(probability, odds)


class TestToDecimal:
    @pytest.mark.parametrize(
        "american,expected",
        [(-500, 1.2), (-200, 1.5), (-110, 1.0 + 100.0 / 110.0), (-100, 2.0), (100, 2.0), (150, 2.5), (500, 6.0)],
    )
    def test_reads_american_prices(self, american, expected):
        assert to_decimal(american) == pytest.approx(expected)

    @pytest.mark.parametrize("decimal", [1.0, 1.01, 1.5, 1.91, 2.5, 40.0, 99.5])
    def test_reads_decimal_prices_unchanged(self, decimal):
        assert to_decimal(decimal) == decimal

    @pytest.mark.parametrize("american", [-500, -200, -110, -100, 100, 120, 150, 300, 1000])
    def test_agrees_with_american_to_decimal(self, american):
        assert to_decimal(american) == american_to_decimal(american)

    @pytest.mark.parametrize("odds", [0.5, 0.999])
    def test_rejects_prices_that_fit_neither_format(self, odds):
        with pytest.raises(ValueError):
            to_decimal(odds)

    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            to_decimal(0)

    @pytest.mark.parametrize("odds", ["2.0", True, None, [2.0]])
    def test_rejects_non_real_values(self, odds):
        with pytest.raises(TypeError):
            to_decimal(odds)

    @pytest.mark.parametrize("odds", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_values(self, odds):
        with pytest.raises(ValueError):
            to_decimal(odds)

    def test_lenient_pricing_wrapper_converts_and_absorbs_errors(self):
        assert _decimal_odds_for_side(150, "A") == pytest.approx(2.5)
        assert _decimal_odds_for_side(2.5, "A") == pytest.approx(2.5)
        assert _decimal_odds_for_side(0.5, "A") is None


class TestLedgerMetrics:
    def test_pnl_sums_a_known_ledger(self):
        assert pnl(LEDGER) == pytest.approx(15.0)

    def test_roi_of_a_known_ledger(self):
        assert roi(LEDGER) == pytest.approx(15.0 / 250.0)

    def test_all_losses_report_negative_return(self):
        ledger = [{"stake": 100.0, "profit": -100.0}, {"stake": 100.0, "profit": -100.0}]
        assert pnl(ledger) == pytest.approx(-200.0)
        assert roi(ledger) == pytest.approx(-1.0)

    def test_records_that_moved_no_money_do_not_distort(self):
        ledger = LEDGER + [
            _record(0.0, 0.0, skipped_zero_stake=True),
            _record(0.0, 0.0, error="strategy exploded"),
        ]
        assert pnl(ledger) == pytest.approx(pnl(LEDGER))
        assert roi(ledger) == pytest.approx(roi(LEDGER))

    def test_empty_ledger(self):
        assert pnl([]) == 0.0
        assert roi([]) == 0.0

    def test_agrees_with_summarize_bet_history(self):
        assert pnl(LEDGER) == summarize_bet_history(LEDGER)["net_profit"]


class TestDecimalOddsPricingPath:
    """Decimal odds price bets exactly where American odds always have."""

    def _run(self, odds_data, fraction=0.1):
        bankroll = BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)
        backtest = Backtest(StubArena())
        backtest.run_explicit(
            {1: [], 2: odds_data},
            FixedFractionForAllBetsStrategy(fraction),
            bankroll,
            period_to_start_betting=1,
        )
        return backtest.bet_history

    def test_decimal_odds_set_the_payoff(self):
        history = self._run([{"winner": "A", "loser": "B", "winner_odds": 2.0, "loser_odds": 2.0}])
        assert len(history) == 2
        assert [record["payoff"] for record in history] == [1.0, 1.0]
        assert [record["stake"] for record in history] == [100.0, 100.0]
        assert [record["won"] for record in history] == [True, False]

    def test_mixed_formats_price_each_side_from_its_own_value(self):
        history = self._run([{"winner": "A", "loser": "B", "winner_odds": 150, "loser_odds": 1.5}])
        payoffs = {record["label"]: record["payoff"] for record in history}
        assert payoffs["A"] == pytest.approx(1.5)  # American 150 -> decimal 2.5
        assert payoffs["B"] == pytest.approx(0.5)  # decimal 1.5

    def test_prices_that_fit_neither_format_are_skipped_with_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="keeks_elote.backtest"):
            history = self._run([{"winner": "A", "loser": "B", "winner_odds": 0.5, "loser_odds": 0.25}])
        assert history == []
        assert any("invalid odds" in record.message for record in caplog.records)
