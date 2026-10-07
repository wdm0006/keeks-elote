"""Integration tests for the weekly-portfolio backtest flow.

These pin the behaviors the weekly portfolio promises on top of keeks 0.9's
allocation layer: no-lookahead rating order, odds-gap exclusion, one batch-net
settlement per week, seeded bit-exact replay, and the weekly ledger schema --
through :class:`keeks_elote.portfolio_backtest.WeeklyPortfolioBacktest`.
"""

import datetime

import pytest
from keeks.bankroll import BankRoll

from keeks_elote.portfolio_backtest import WeeklyPortfolioBacktest

STARTING_FUNDS = 1000.0

LEDGER_KEYS = {
    "period",
    "bets",
    "weights",
    "stakes",
    "stake",
    "returns",
    "won",
    "profit",
    "bankroll_before",
    "bankroll_after",
    "skipped_zero_stake",
    "error",
}


class DriftingArena:
    """Deterministic arena whose probabilities drift with every rated game.

    ``expected_score`` returns ``base + drift * (number of games rated so
    far)``, so a probability quoted in the ledger pins exactly how many games
    had been rated when the week was priced -- the no-lookahead probe.
    """

    def __init__(self, base: float = 0.5, drift: float = 0.05):
        self.base = base
        self.drift = drift
        self.matchups = []

    def expected_score(self, home, away):
        return self.base + self.drift * len(self.matchups)

    def tournament(self, matchups):
        self.matchups.extend(matchups)


class FixedWeightsAllocator:
    """Duck-typed allocator quoting one fixed weight vector."""

    def __init__(self, weights):
        self.weights = tuple(weights)

    def evaluate(self, current_bankroll):
        return self.weights


class BoomAllocator:
    """Duck-typed allocator whose evaluation always raises."""

    def evaluate(self, current_bankroll):
        raise RuntimeError("allocator exploded")


def fixed_weights_factory(fraction):
    """Builds a factory handing every week's slate the same per-bet weight."""

    def factory(model):
        return FixedWeightsAllocator([fraction] * len(model.bets))

    return factory


def zero_weights_factory(model):
    return FixedWeightsAllocator([0.0] * len(model.bets))


def one_bump_factory(raising_period):
    """Builds a factory that raises in one period and quotes 10% elsewhere."""
    state = {"seen": {}}

    def factory(model):
        bets = [bet[0] for bet in model.bets]
        period = state["seen"].get("count", 0)
        state["seen"]["count"] = period + 1
        if period == raising_period:
            return BoomAllocator()
        return FixedWeightsAllocator([0.1] * len(bets))

    return factory


def recording_bankroll(**kwargs):
    """A ``BankRoll`` that records every deposit/withdraw/bet call."""

    class RecordingBankRoll(BankRoll):
        def __init__(self, *args, **kwds):
            super().__init__(*args, **kwds)
            self.transactions = []

        def deposit(self, amount):
            self.transactions.append(("deposit", amount))
            return super().deposit(amount)

        def withdraw(self, amount):
            self.transactions.append(("withdraw", amount))
            return super().withdraw(amount)

        def bet(self, amount):
            self.transactions.append(("bet", amount))
            return super().bet(amount)

    return RecordingBankRoll(**kwargs)


def game(winner, loser, winner_ml=150, week=1, date=None):
    """One priced game; ``winner_ml=None`` models the fixture's odds gaps."""
    record = {"winner": winner, "loser": loser, "winner_score": 21, "loser_score": 14}
    if winner_ml is not None:
        record["winner_ml"] = winner_ml
    if date is not None:
        record["date"] = date
    return record


def three_week_schedule(winner_ml=150):
    """Three weeks of one priced game each; every week is a betting week."""
    return {
        1: [game("A", "B", winner_ml)],
        2: [game("B", "C", winner_ml)],
        3: [game("C", "A", winner_ml)],
    }


def run(data, factory=None, seed=123, **kwargs):
    backtest = WeeklyPortfolioBacktest(DriftingArena())
    bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
    history = backtest.run_explicit(data, factory or fixed_weights_factory(0.1), bankroll, seed=seed, **kwargs)
    return backtest, bankroll, history


class TestTimeStampedRating:
    """A fully dated schedule rates from the fixture's calendar, not the wall clock."""

    def test_dated_games_rate_with_their_kickoff(self):
        """Every dated game rates as a (a, b, attributes, match_time) matchup."""
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        schedule = {
            1: [game("A", "B", date="20170902")],
            2: [game("B", "C", date="20170909")],
        }
        backtest.run_explicit(schedule, fixed_weights_factory(0.1), bankroll, seed=123)

        assert len(arena.matchups) == 2
        assert arena.matchups[0][:2] == ("A", "B")
        assert arena.matchups[0][3] == datetime.datetime(2017, 9, 2)
        assert arena.matchups[1][:2] == ("B", "C")
        assert arena.matchups[1][3] == datetime.datetime(2017, 9, 9)

    def test_a_week_rates_in_kickoff_order(self):
        """Fixture order is not chronological; elote rejects out-of-order match times."""
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        schedule = {
            1: [
                game("A", "B", date="20170903"),
                game("C", "D", date="20170902"),
            ],
        }
        backtest.run_explicit(schedule, fixed_weights_factory(0.1), bankroll, seed=123)

        assert [matchup[3] for matchup in arena.matchups] == [
            datetime.datetime(2017, 9, 2),
            datetime.datetime(2017, 9, 3),
        ]

    def test_undated_schedules_rate_without_times(self):
        """A schedule with no dates keeps the plain-matchup convention."""
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        backtest.run_explicit(three_week_schedule(), fixed_weights_factory(0.1), bankroll, seed=123)

        assert [matchup[:2] for matchup in arena.matchups] == [("A", "B"), ("B", "C"), ("C", "A")]
        assert all(matchup[3] is None for matchup in arena.matchups)

    def test_one_undated_game_switches_the_whole_run_to_wall_clock(self):
        """The two clocks never mix: any undated game reverts the entire run."""
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        schedule = {
            1: [game("A", "B", date="20170902")],
            2: [game("B", "C")],
        }
        backtest.run_explicit(schedule, fixed_weights_factory(0.1), bankroll, seed=123)

        assert [matchup[:2] for matchup in arena.matchups] == [("A", "B"), ("B", "C")]
        assert all(matchup[3] is None for matchup in arena.matchups)


class TestNoLookaheadRatingOrder:
    """A week's slate is priced from the ratings as they stood before it played."""

    def test_each_week_is_priced_from_prior_weeks_ratings_only(self):
        arena = DriftingArena(base=0.5, drift=0.05)
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        backtest.run_explicit(three_week_schedule(), fixed_weights_factory(0.1), bankroll, seed=123)

        # One game per week: week 1 prices from zero rated games (p=0.50),
        # week 2 from one (p=0.55), week 3 from two (p=0.60). A run that rated
        # a week's games before pricing them would show the drift already
        # applied to its own week.
        assert [record["bets"][0]["probability"] for record in backtest.bet_history] == pytest.approx([0.5, 0.55, 0.6])

    def test_a_weeks_games_rate_only_after_its_week_settles(self):
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        history = backtest.run_explicit(three_week_schedule(), fixed_weights_factory(0.1), bankroll, seed=123)

        # Every week settled before its game was rated: the ledger ends with
        # all three games rated, and the last week's pricing (checked above)
        # saw only two of them.
        assert len(arena.matchups) == 3
        assert len(history) == 3


class TestOddsGapExclusion:
    """Games without a usable winner_ml are rated but never bet."""

    def test_gapped_game_is_rated_but_excluded_from_the_slate(self):
        data = {
            1: [game("A", "B", 150), game("C", "D", None)],
        }
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        backtest.run_explicit(data, fixed_weights_factory(0.1), bankroll, seed=123)

        assert len(backtest.bet_history) == 1
        assert [bet["label"] for bet in backtest.bet_history[0]["bets"]] == ["A"]
        # The gapped game still rated: it is a real game, just not bettable.
        assert len(arena.matchups) == 2

    def test_string_moneylines_parse_like_the_fixture_encodes_them(self):
        # The CFB fixture stores prices as strings ("+150"); the module coerces
        # them to numbers before format detection.
        data = {1: [game("A", "B", "+150"), game("C", "D", "-100")]}
        backtest, bankroll, history = run(data)
        assert len(history) == 1
        assert [bet["payoff"] for bet in history[0]["bets"]] == pytest.approx([2.5, 2.0])

    def test_a_week_with_no_bettable_games_leaves_no_record(self):
        data = {
            1: [game("A", "B", 150)],
            2: [game("C", "D", None), game("E", "F", float("inf"))],
        }
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        history = backtest.run_explicit(data, fixed_weights_factory(0.1), bankroll, seed=123)

        assert [record["period"] for record in history] == [1]
        # Week 2's games still rated.
        assert len(arena.matchups) == 3


class TestOneSettlementPerWeek:
    """One week is one portfolio decision: one batch-net settlement, one trial."""

    def test_the_bankroll_moves_at_most_once_per_week(self):
        backtest, bankroll, history = run(three_week_schedule())
        assert len(history) == 3
        # Each week settles as one batch: a single deposit or withdrawal for
        # the net, never one transaction per bet.
        assert len(bankroll.transactions) == 3
        assert {kind for kind, _ in bankroll.transactions} <= {"deposit", "withdraw"}

    def test_profit_telescopes_to_the_batch_accounting(self):
        backtest, bankroll, history = run(three_week_schedule())
        for record in history:
            if record["skipped_zero_stake"]:
                assert record["profit"] == 0.0
                continue
            # stakes x returns is the exact batch arithmetic; the bankroll
            # reads are rounded to cents, so agreement is only to that cent.
            exact = sum(stake * pct for stake, pct in zip(record["stakes"], record["returns"], strict=True))
            assert record["profit"] == pytest.approx(exact, abs=0.011)
            assert record["bankroll_after"] == pytest.approx(record["bankroll_before"] + record["profit"], abs=0.011)

    def test_stakes_are_bettable_funds_times_the_weights(self):
        backtest, bankroll, history = run(three_week_schedule())
        for record in history:
            for stake, weight in zip(record["stakes"], record["weights"], strict=True):
                assert stake == pytest.approx(record["bankroll_before"] * bankroll.percent_bettable * weight)


class TestSeededReplay:
    """A seeded run replays bit-exactly; different seeds diverge."""

    def test_same_seed_replays_identically(self):
        _, _, first = run(three_week_schedule(), seed=123)
        _, _, second = run(three_week_schedule(), seed=123)
        assert first == second

    def test_different_seed_settles_differently(self):
        _, _, first = run(three_week_schedule(), seed=123)
        _, _, second = run(three_week_schedule(), seed=124)
        assert first != second

    def test_changing_the_betting_start_does_not_shift_any_weeks_stream(self):
        # Week streams key off schedule position, not off where betting starts:
        # warm-up weeks construct no simulator and draw nothing, so a week that
        # bets under both settings settles from the same stream.
        data = three_week_schedule()
        _, _, early = run(data, seed=123, period_to_start_betting=0)
        _, _, late = run(data, seed=123, period_to_start_betting=1)
        common = (2, 3)
        assert [record["returns"] for record in early if record["period"] in common] == [
            record["returns"] for record in late if record["period"] in common
        ]
        assert [record["returns"] for record in late if record["period"] in common] != [
            record["returns"] for record in early
        ]


class TestWarmUpPeriods:
    """Warm-up weeks rate but never bet."""

    def test_warm_up_weeks_leave_no_ledger_record(self):
        data = three_week_schedule()
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        history = backtest.run_explicit(data, fixed_weights_factory(0.1), bankroll, period_to_start_betting=1, seed=123)

        assert [record["period"] for record in history] == [2, 3]
        # Week 1 rated in warm-up, so weeks 2 and 3 price from 1 and 2 rated games.
        assert [record["bets"][0]["probability"] for record in history] == pytest.approx([0.55, 0.6])
        assert len(arena.matchups) == 3


class TestAllocatorFactoryContract:
    """The factory sizes each week's model; failures are recorded, not fatal."""

    def test_the_factory_receives_one_model_per_betting_week(self):
        models = []
        data = three_week_schedule()
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)

        def factory(model):
            models.append(model)
            return FixedWeightsAllocator([0.1] * len(model.bets))

        backtest.run_explicit(data, factory, bankroll, seed=123)
        assert len(models) == 3
        for model, record in zip(models, backtest.bet_history, strict=True):
            assert len(model.bets) == len(record["bets"])

    def test_an_allocator_that_raises_is_recorded_and_the_run_continues(self):
        # The factory's call count is the betting week's schedule position, so
        # raising_period=0 explodes in the first betting week (period 1).
        backtest, bankroll, history = run(three_week_schedule(), factory=one_bump_factory(raising_period=0), seed=123)

        assert len(history) == 3
        assert history[0]["error"] == "allocator exploded"
        assert history[0]["weights"] is None
        assert history[0]["stake"] == 0.0
        assert history[0]["profit"] == 0.0
        # The failed week's bankroll is untouched and the run continued.
        assert history[0]["bankroll_after"] == pytest.approx(STARTING_FUNDS)
        assert history[1]["error"] is None
        assert history[1]["stake"] > 0.0

    def test_zero_weights_are_a_skipped_week_that_still_rates(self):
        data = three_week_schedule()
        arena = DriftingArena()
        backtest = WeeklyPortfolioBacktest(arena)
        bankroll = recording_bankroll(initial_funds=STARTING_FUNDS, percent_bettable=1.0, max_transaction_loss=None)
        history = backtest.run_explicit(data, zero_weights_factory, bankroll, seed=123)

        assert len(history) == 3
        assert all(record["skipped_zero_stake"] for record in history)
        assert all(record["returns"] is None for record in history)
        assert all(record["profit"] == 0.0 for record in history)
        # Declined bets still rated their games.
        assert len(arena.matchups) == 3


class TestWeeklyLedgerSchema:
    """The weekly ledger's shape, and the summarize_bet_history contract."""

    def test_every_record_carries_the_documented_schema(self):
        backtest, bankroll, history = run(three_week_schedule())
        for record in history:
            assert set(record) == LEDGER_KEYS
            assert len(record["weights"]) == len(record["bets"])
            assert len(record["stakes"]) == len(record["bets"])
            assert len(record["returns"]) == len(record["bets"])
            assert record["won"] == (record["profit"] > 0.0)
        # Returned history is the stored history.
        assert history == backtest.bet_history

    def test_the_ledger_flows_through_the_shared_summary_helper(self):
        from keeks_elote.backtest import summarize_bet_history

        backtest, bankroll, history = run(three_week_schedule())
        summary = summarize_bet_history(backtest.bet_history)
        assert summary["total_candidates"] == 3
        assert summary["net_profit"] == pytest.approx(bankroll.total_funds - STARTING_FUNDS)


class OnlineAllocator(FixedWeightsAllocator):
    """A duck-typed online allocator that also tracks the bankroll updates it is told about."""

    def __init__(self, weights):
        super().__init__(weights)
        self.updates = []

    def update_bankroll(self, total_funds):
        self.updates.append(total_funds)


class TestOnlineAllocatorHook:
    """Stateful allocators follow the run's bankroll through the forwarded hook."""

    def test_an_allocator_with_update_bankroll_sees_one_call_per_settled_week(self):
        # The factory returns the SAME instance every week -- the shape that
        # keeps an online allocator's state across weeks.
        allocator = OnlineAllocator([0.1])

        def factory(model):
            return allocator

        backtest, bankroll, history = run(three_week_schedule(), factory=factory)

        assert len(history) == 3
        assert len(allocator.updates) == 3
        assert all(isinstance(update, float) and update > 0 for update in allocator.updates)

    def test_an_allocator_without_the_hook_is_unaffected(self):
        backtest, bankroll, history = run(three_week_schedule())
        assert len(history) == 3
        assert all(record["error"] is None for record in history)
