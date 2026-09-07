"""Integration tests: the advertised rating systems on real elote arenas.

The unit suites exercise the margin-aware 6-tuple path against recording stubs; these
tests run Massey, Keener and Pythagorean -- the margin-aware systems the package
advertises -- through real elote ``LambdaArena`` instances, so the score pair
forwarded positionally in the matchup tuple must actually move the ratings.
"""

import logging

import pytest
from elote.arenas.lambda_arena import LambdaArena
from elote.competitors.keener import KeenerCompetitor
from elote.competitors.massey import MasseyCompetitor
from elote.competitors.pythagorean import PythagoreanCompetitor
from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

from keeks_elote import Backtest

MARGIN_AWARE_SYSTEMS = [MasseyCompetitor, KeenerCompetitor, PythagoreanCompetitor]

PROJECTION_KEYS = {"period", "predicted_winner", "predicted_loser", "probability"}
BET_RECORD_KEYS = {
    "period",
    "label",
    "opponent",
    "fraction",
    "stake",
    "payoff",
    "won",
    "profit",
    "bankroll_after",
    "skipped_zero_stake",
    "error",
}


def _no_comparison(_a, _b):
    """Ground-truth guard: a recorded result must never be re-decided by the lambda."""
    raise AssertionError("the arena's comparison function decided a game that had a recorded winner")


def _arena(competitor_class):
    return LambdaArena(_no_comparison, base_competitor=competitor_class)


def _season_data():
    """A tiny season with real margins: A is dominant, B edges C by a single point."""
    return {
        1: [{"winner": "A", "loser": "B", "winner_score": 35, "loser_score": 10}],
        2: [
            {"winner": "A", "loser": "C", "winner_score": 28, "loser_score": 14},
            {"winner": "B", "loser": "C", "winner_score": 21, "loser_score": 20},
        ],
    }


def _without_scores(data):
    """The same results with scores stripped, so ratings come from unit margins."""
    return {
        period: [{key: value for key, value in game.items() if not key.endswith("_score")} for game in games]
        for period, games in data.items()
    }


@pytest.mark.parametrize("competitor_class", MARGIN_AWARE_SYSTEMS)
def test_projections_are_structured_records(competitor_class):
    """run_and_project returns one record per projected game, not just log lines."""
    projections = Backtest(_arena(competitor_class)).run_and_project(_season_data())

    assert [record["period"] for record in projections] == [2, 2]
    assert all(set(record) == PROJECTION_KEYS for record in projections)
    assert all(0.5 <= record["probability"] <= 1.0 for record in projections)

    # The dominant team is favored over an unrated opponent by every margin-aware
    # system, from period-1 ratings alone.
    assert (projections[0]["predicted_winner"], projections[0]["predicted_loser"]) == ("A", "C")

    # The other matchup is between a just-battered B and an unrated C: assert only
    # that the record names one of the two sides with the opposing probability.
    assert {projections[1]["predicted_winner"], projections[1]["predicted_loser"]} == {"B", "C"}


@pytest.mark.parametrize("competitor_class", MARGIN_AWARE_SYSTEMS)
def test_projection_log_lines_are_kept(caplog, competitor_class):
    """The human-readable prediction logs survive alongside the structured return."""
    with caplog.at_level(logging.INFO, logger="keeks_elote.backtest"):
        projections = Backtest(_arena(competitor_class)).run_and_project(_season_data())

    assert any("Predicted A over C: " in record.message for record in caplog.records)
    assert len(projections) == 2


@pytest.mark.parametrize("competitor_class", MARGIN_AWARE_SYSTEMS)
def test_scores_reach_the_rating_math(competitor_class):
    """Identical results, different margins: the score pair must move the ratings."""
    margin_arena = _arena(competitor_class)
    unit_arena = _arena(competitor_class)

    Backtest(margin_arena).run_and_project(_season_data())
    Backtest(unit_arena).run_and_project(_without_scores(_season_data()))

    # A's 25-point blowout of B must be visible in the ratings when the scores flow,
    # and the unit-margin path (a bare +1/-1 for the same result) must not reproduce it.
    with_scores = margin_arena.expected_score("A", "B")
    without_scores = unit_arena.expected_score("A", "B")

    assert with_scores > without_scores


@pytest.mark.parametrize("competitor_class", MARGIN_AWARE_SYSTEMS)
def test_margin_ratings_drive_a_full_betting_run(competitor_class):
    """run_explicit prices, settles and ledgers bets over real margin-aware ratings."""
    data = {
        1: [
            {
                "winner": "A",
                "loser": "B",
                "winner_score": 35,
                "loser_score": 10,
                "winner_odds": -110,
                "loser_odds": -110,
            }
        ],
        2: [
            {
                "winner": "A",
                "loser": "C",
                "winner_score": 28,
                "loser_score": 14,
                "winner_odds": -110,
                "loser_odds": -110,
            }
        ],
        3: [
            {
                "winner": "B",
                "loser": "C",
                "winner_score": 21,
                "loser_score": 20,
                "winner_odds": -110,
                "loser_odds": -110,
            }
        ],
    }
    bankroll = BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_draw_down=1.0)
    backtest = Backtest(_arena(competitor_class))

    result = backtest.run_explicit(
        data,
        KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0),
        bankroll,
        period_to_start_betting=1,
    )

    summary = backtest.run_summary()
    assert result is bankroll
    # A's period-1 blowout prices the period-2 A/C bet positive-EV for every one of
    # these systems at -110, so each run must place at least one bet and fail none.
    assert summary["placed_bets"] >= 1
    assert summary["failed_bets"] == 0
    assert summary["net_profit"] == pytest.approx(sum(record["profit"] for record in backtest.bet_history))
    for record in backtest.bet_history:
        assert set(record) == BET_RECORD_KEYS
