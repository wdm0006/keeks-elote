"""Integration tests for the 1X2 (multi-outcome) backtest flow.

These exercise the Phase 3 load-bearing assumption -- keeks-elote call sites
can consume the keeks multi-outcome API -- through
:class:`keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest`, including the
known-ledger settlement-accounting test. The flow needs ``keeks.multi_outcome``,
which first ships in keeks 0.8.0 (not on PyPI yet, install keeks from git
main); the module skips with a reason on every keeks release that lacks it.
"""

import pytest

pytest.importorskip(
    "keeks.multi_outcome",
    reason="keeks.multi_outcome needs keeks >= 0.8.0, which is not on PyPI yet; install keeks from git main (make install)",
)

import numpy as np  # noqa: E402
from keeks.bankroll import BankRoll  # noqa: E402
from keeks.multi_outcome import MultiOutcomeKellyCriterion  # noqa: E402

from keeks_elote import create_arena, pnl  # noqa: E402
from keeks_elote.backtest import roi  # noqa: E402
from keeks_elote.multi_outcome_backtest import (  # noqa: E402
    MultiOutcomeBacktest,
    one_x_two_probabilities,
)

STARTING_FUNDS = 1000.0


class StubArena:
    """Deterministic stand-in for an elote arena that records what it is fed."""

    def __init__(self, p_home: float = 0.6):
        self.p_home = p_home
        self.matchups = []

    def expected_score(self, home, away):
        return self.p_home

    def tournament(self, matchups):
        self.matchups.extend(matchups)


class FixedFractionStrategy:
    """Duck-typed strategy quoting a fixed fraction on every leg."""

    def __init__(self, fraction: float = 0.1):
        self.fraction = fraction

    def evaluate(self, probabilities, current_bankroll):
        return [self.fraction] * len(probabilities)


class BoomStrategy:
    """Duck-typed strategy whose evaluation always raises."""

    def evaluate(self, probabilities, current_bankroll):
        raise RuntimeError("strategy exploded")


def game(home, away, home_score, away_score, home_odds=3.0, draw_odds=3.2, away_odds=2.5, **overrides):
    """Builds one 1X2 game record with configurable pieces."""
    record = {"home": home, "away": away, "home_score": home_score, "away_score": away_score}
    for key, value in overrides.items():
        if value is not None:
            record[key] = value
    if home_odds is not None:
        record["home_odds"] = home_odds
    if draw_odds is not None:
        record["draw_odds"] = draw_odds
    if away_odds is not None:
        record["away_odds"] = away_odds
    return record


def realized_leg_from_seed(seed: int, book) -> int:
    """Reproduces the simulator's documented public seeding and categorical draw.

    The multi-outcome simulator seeds each trial from a spawned ``SeedSequence``
    stream and realizes the first leg whose cumulative probability band
    contains the uniform draw -- the contract its docstrings promise, which
    this test reads rather than any private helper.
    """
    stream = np.random.SeedSequence(seed).spawn(1)[0]
    draw = np.random.default_rng(stream).random()
    cumulative = np.cumsum(book)
    return next(index for index, bound in enumerate(cumulative) if draw < bound)


class TestOneXTwoProbabilities:
    """Unit tests for the draw-aware 1X2 book construction."""

    def test_book_sums_to_one(self):
        for p_home in (0.0, 0.1, 0.5, 0.9, 1.0):
            book = one_x_two_probabilities(p_home)
            assert sum(book) == pytest.approx(1.0)

    def test_at_parity_draw_rate_is_the_whole_draw_mass(self):
        book = one_x_two_probabilities(0.5, draw_rate=0.3)
        assert book == pytest.approx((0.35, 0.3, 0.35))

    def test_favorites_draw_less(self):
        even = one_x_two_probabilities(0.5)
        lopsided = one_x_two_probabilities(0.9)
        assert lopsided[1] < even[1]
        assert lopsided[0] > even[0]

    def test_extremes_keep_all_mass_on_one_leg(self):
        assert one_x_two_probabilities(1.0) == pytest.approx((1.0, 0.0, 0.0))
        assert one_x_two_probabilities(0.0) == pytest.approx((0.0, 0.0, 1.0))

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            one_x_two_probabilities(1.5)
        with pytest.raises(ValueError):
            one_x_two_probabilities(0.5, draw_rate=-0.1)
        with pytest.raises(TypeError):
            one_x_two_probabilities("half")


def two_period_schedule():
    """Two periods of two priced games each; period 0 is warm-up."""
    return {
        0: [game("Alpha", "Beta", 2, 1), game("Gamma", "Delta", 1, 1)],
        1: [game("Alpha", "Gamma", 0, 1), game("Beta", "Delta", 1, 0)],
    }


class TestExactlyOneSettlementLedger:
    """The known-ledger settlement accounting test.

    A fixed-fraction strategy stakes 10% of the bankroll on each of the three
    legs of every game priced (3.0, 3.2, 2.5); the arena's book is fixed at
    (0.456, 0.24, 0.304). With those numbers the ledger is computable by
    hand, so each entry is checked against exactly-one-settlement accounting:
    one leg realized as a win, the other staked legs realized as losses, and
    no leg settling twice.
    """

    BOOK = one_x_two_probabilities(0.6, draw_rate=0.25)  # (0.456, 0.24, 0.304)

    def run(self, seed):
        backtest = MultiOutcomeBacktest(StubArena(), draw_rate=0.25)
        bankroll = BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None)
        backtest.run_explicit(
            two_period_schedule(), FixedFractionStrategy(0.1), bankroll, period_to_start_betting=0, seed=seed
        )
        return backtest, bankroll

    def test_warm_up_period_bets_nothing(self):
        backtest, _ = self.run(seed=2026)
        assert [record["period"] for record in backtest.bet_history] == [1, 1]

    def test_known_ledger_settlement_accounting(self):
        schedule = two_period_schedule()
        warm_up_games = sum(len(games) for period, games in schedule.items() if period <= 0)
        backtest, bankroll = self.run(seed=2026)

        expected_bankroll = STARTING_FUNDS
        for ledger_index, record in enumerate(backtest.bet_history):
            # The flow seeds by schedule index -- warm-up games consume
            # indices too -- so the n-th settled record is schedule game
            # warm_up_games + n.
            schedule_index = warm_up_games + ledger_index
            won_leg = realized_leg_from_seed(2026 + schedule_index, self.BOOK)

            # The bankroll before the trial, and the stakes it prices.
            bankroll_before = round(expected_bankroll, 2)
            bettable = round(bankroll_before * 1.0, 2)
            stakes = tuple(round(bettable * 0.1, 2) for _ in range(3))

            # Exactly-one-settlement accounting: one leg won at its decimal
            # payoff, every other staked leg lost at its full stake.
            returns = [-1.0 * stake / bankroll_before for stake in stakes]
            returns[won_leg] = record["payoffs"][won_leg] * stakes[won_leg] / bankroll_before
            profit = record["payoffs"][won_leg] * stakes[won_leg] - sum(stakes) + stakes[won_leg]

            assert record["won_leg"] == won_leg
            assert record["probabilities"] == pytest.approx(self.BOOK)
            assert record["payoffs"] == pytest.approx((3.0, 3.2, 2.5))
            assert record["stakes"] == pytest.approx(stakes)
            assert record["stake"] == pytest.approx(sum(stakes))
            assert record["bankroll_before"] == pytest.approx(bankroll_before)
            assert record["bankroll_after"] == pytest.approx(bankroll_before + profit)
            assert record["profit"] == pytest.approx(profit)
            assert record["returns"] == pytest.approx(returns)
            assert record["error"] is None

            expected_bankroll += profit

        assert bankroll.total_funds == pytest.approx(expected_bankroll)

    def test_exactly_one_positive_return_per_settled_trial(self):
        backtest, _ = self.run(seed=2026)
        for record in backtest.bet_history:
            assert record["won_leg"] in (0, 1, 2)
            positive_returns = [pct for pct in record["returns"] if pct > 0]
            assert len(positive_returns) == 1
            # No leg settles twice: the won leg is the only one that is not a
            # full-stake loss.
            for leg, pct in enumerate(record["returns"]):
                if leg != record["won_leg"]:
                    assert pct == pytest.approx(-record["stakes"][leg] / record["bankroll_before"])

    def test_ledger_telescopes_to_the_bankroll(self):
        backtest, bankroll = self.run(seed=2026)
        settled = [record for record in backtest.bet_history if record["error"] is None and record["stake"] > 0]
        assert sum(record["profit"] for record in settled) == pytest.approx(bankroll.total_funds - STARTING_FUNDS)
        assert pnl(backtest.bet_history) == pytest.approx(bankroll.total_funds - STARTING_FUNDS)

    def test_seeded_runs_replay_identically(self):
        first_backtest, first_bankroll = self.run(seed=2026)
        second_backtest, second_bankroll = self.run(seed=2026)
        assert first_backtest.bet_history == second_backtest.bet_history
        assert first_bankroll.total_funds == second_bankroll.total_funds


class TestFlowEndToEnd:
    """The full flow with the real arena and the real keeks Kelly strategy."""

    SCHEDULE = {
        0: [game("City", "Rovers", 2, 0), game("United", "Wanderers", 1, 1)],
        1: [game("City", "United", 1, 2), game("Rovers", "Wanderers", 3, 3)],
        2: [
            game("United", "City", 2, 2, home_odds=2.2, draw_odds=3.4, away_odds=2.9),
            game("Wanderers", "Rovers", 0, 1),
        ],
    }

    def run(self, seed=None):
        backtest = MultiOutcomeBacktest(create_arena("elo"), draw_rate=0.25)
        bankroll = BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=0.5, max_draw_down=None)
        strategy = MultiOutcomeKellyCriterion(payoffs=(2.0, 3.0, 3.0), loss=1.0)
        backtest.run_explicit(self.SCHEDULE, strategy, bankroll, period_to_start_betting=1, seed=seed)
        return backtest, bankroll, strategy

    def test_caller_strategy_is_never_reassigned_odds(self):
        backtest, _, strategy = self.run(seed=11)
        # The flow reprices by fresh construction per game; the caller's
        # instance must keep the payoffs it was constructed with.
        assert strategy.payoffs == (2.0, 3.0, 3.0)
        assert all(record["error"] is None for record in backtest.bet_history)

    def test_every_quoted_book_is_valid_and_fully_settled(self):
        backtest, bankroll, _ = self.run(seed=11)
        settled = [record for record in backtest.bet_history if record["stake"] > 0]
        assert settled, "the Kelly strategy should find at least one priced leg to stake"
        for record in settled:
            fractions = record["fractions"]
            assert fractions is not None and len(fractions) == 3
            assert all(0.0 <= fraction <= 1.0 for fraction in fractions)
            assert sum(fractions) <= 1.0 + 1e-9
            assert record["won_leg"] in (0, 1, 2)
            # Exactly-one-settlement accounting, per leg: the realized leg
            # pays its decimal payoff on whatever was staked there (0.0 when
            # the strategy staked nothing on the realized leg), every other
            # leg settles as a loss on its stake. The return identity holds
            # whether or not the winning leg carried money.
            before = record["bankroll_before"]
            expected_returns = tuple(
                record["payoffs"][leg] * stake / before if leg == record["won_leg"] else -stake / before
                for leg, stake in enumerate(record["stakes"])
            )
            assert record["returns"] == pytest.approx(expected_returns)
            # keeks rounds bankroll reads to cents, so the exact settlement
            # returns reconcile with the rounded-read profit only to within
            # that cent (two rounded reads per record).
            profit_from_returns = sum(pct * before for pct in record["returns"])
            assert profit_from_returns == pytest.approx(record["profit"], abs=0.02)

        assert sum(record["profit"] for record in settled) == pytest.approx(bankroll.total_funds - STARTING_FUNDS)
        assert roi(backtest.bet_history) == pytest.approx(
            pnl(backtest.bet_history) / sum(record["stake"] for record in settled)
        )


class TestRatingAndLedgerBoundaries:
    """What gets rated, what gets bet, and what gets skipped entirely."""

    def test_draws_are_rated_as_draws(self):
        arena = StubArena()
        backtest = MultiOutcomeBacktest(arena, draw_rate=0.25)
        backtest.run_explicit(
            {0: [game("A", "B", 1, 1), game("C", "D", 2, 0), game("E", "F", 0, 1)]},
            FixedFractionStrategy(0.1),
            BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None),
            period_to_start_betting=10,
            seed=1,
        )
        assert len(arena.matchups) == 3
        # (home, away, attributes, match_time, outcome, scores) -- a draw
        # forwards outcome 0.5 with the equal score pair.
        draw_matchup = arena.matchups[0]
        assert draw_matchup[0] == "A" and draw_matchup[1] == "B"
        assert draw_matchup[4] == 0.5 and draw_matchup[5] == (1.0, 1.0)
        assert arena.matchups[1][4] == 1.0
        assert arena.matchups[2][4] == 0.0
        assert backtest.bet_history == []

    def test_game_without_usable_scores_is_not_rated_or_bet(self):
        arena = StubArena()
        backtest = MultiOutcomeBacktest(arena, draw_rate=0.25)
        backtest.run_explicit(
            {0: [game("A", "B", None, None)]},
            FixedFractionStrategy(0.1),
            BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None),
            period_to_start_betting=10,
            seed=1,
        )
        assert arena.matchups == []
        assert backtest.bet_history == []

    def test_game_missing_one_price_is_rated_but_not_bet(self):
        arena = StubArena()
        backtest = MultiOutcomeBacktest(arena, draw_rate=0.25)
        backtest.run_explicit(
            {1: [game("A", "B", 1, 0, draw_odds=None)]},
            FixedFractionStrategy(0.1),
            BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None),
            period_to_start_betting=0,
            seed=1,
        )
        assert len(arena.matchups) == 1
        assert backtest.bet_history == []

    def test_strategy_failure_is_recorded_and_the_run_continues(self):
        backtest = MultiOutcomeBacktest(StubArena(), draw_rate=0.25)
        bankroll = BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None)
        backtest.run_explicit(
            {1: [game("A", "B", 1, 0), game("C", "D", 2, 1)]},
            BoomStrategy(),
            bankroll,
            period_to_start_betting=0,
            seed=1,
        )
        assert len(backtest.bet_history) == 2
        for record in backtest.bet_history:
            assert record["error"] == "strategy exploded"
            assert record["fractions"] is None
            assert record["stake"] == 0.0
            assert record["profit"] == 0.0
            assert record["won_leg"] is None
        assert bankroll.total_funds == STARTING_FUNDS

    def test_zero_fraction_quotes_are_flagged_as_skipped(self):
        backtest = MultiOutcomeBacktest(StubArena(), draw_rate=0.25)
        bankroll = BankRoll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_draw_down=None)
        backtest.run_explicit(
            {1: [game("A", "B", 1, 0)]},
            FixedFractionStrategy(0.0),
            bankroll,
            period_to_start_betting=0,
            seed=1,
        )
        assert len(backtest.bet_history) == 1
        record = backtest.bet_history[0]
        assert record["skipped_zero_stake"] is True
        assert record["fractions"] == (0.0, 0.0, 0.0)
        assert record["won_leg"] is None
        assert record["profit"] == 0.0
        assert bankroll.total_funds == STARTING_FUNDS

    def test_draw_rate_is_validated_at_construction(self):
        with pytest.raises(ValueError):
            MultiOutcomeBacktest(StubArena(), draw_rate=1.5)
