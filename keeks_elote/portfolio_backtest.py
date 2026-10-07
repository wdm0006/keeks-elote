"""Weekly-portfolio backtesting: each period's slate of games sized as one joint decision.

:mod:`keeks_elote.backtest` sizes bets one at a time: a strategy quotes a stake per
game against the bankroll, and each game settles independently. This module sizes
the whole slate at once, which is the shape a football week actually presents --
N simultaneous games, one bankroll decision, one settlement batch. It consumes
keeks 0.9's allocation layer (:mod:`keeks.allocation`): the week's arena
probabilities and posted American moneylines become a
:class:`keeks.allocation.BinaryBetsModel`, an allocator
(:class:`keeks.allocation.BaseAllocationStrategy`) weights the whole slate at
once, and a one-trial :class:`keeks.allocation.AllocationSimulator` settles the
week batch-net through the shared :class:`keeks.bankroll.BankRoll`.

The two engines are deliberately siblings over identical inputs -- same schedule,
same ratings, same bankroll conventions -- so a per-bet run and a weekly-portfolio
run over one fixture can be compared side by side; ``examples/cfb_weekly_portfolio.py``
is that comparison.
"""

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from keeks.allocation import AllocationSimulator, BaseAllocationStrategy, BinaryBetsModel
from keeks.bankroll import BankRoll

from keeks_elote.backtest import MatchupTuple, _matchup_tuple, to_decimal
from keeks_elote.data_handling import prepare_data
from keeks_elote.model_evaluation import calculate_probabilities
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord

logger = logging.getLogger(__name__)


#: Maps the week's joint-return model to the allocator that sizes it. A callable,
#: because the slate's width changes from week to week as games gain, lose, or carry
#: no usable moneyline -- and every shipped allocator fixes its weight-vector width
#: at construction from that week's moments or scenarios.
AllocatorFactory = Callable[[BinaryBetsModel], BaseAllocationStrategy]


def _decimal_for_winner(game: GameRecord) -> Optional[float]:
    """Converts the game's winner-side price to decimal odds, or ``None`` when unbettable.

    The posted ``winner_ml`` may be absent, or a non-numeric or non-finite value --
    the CFB fixture has gaps and encodes its prices as strings (``"+150"``) -- so
    the value is first strictly coerced to a real number, then format-detected by
    :func:`to_decimal`. A game without a usable price is excluded from its week's
    slate (warned) while still being rated, mirroring how the per-bet backtest
    skips unpriced sides.
    """
    odds: Any = game.get("winner_ml")
    try:
        return to_decimal(float(odds))
    except (TypeError, ValueError, OverflowError) as exc:
        logger.warning(
            "Excluding %s vs %s from the slate: unusable winner_ml %r (%s).",
            game.get("winner"),
            game.get("loser"),
            odds,
            exc,
        )
        return None


def _match_time(game: GameRecord) -> Optional[datetime.datetime]:
    """Parses the game's kickoff (``"%Y%m%d"`` fixture dates), or ``None`` when undated."""
    date: Any = game.get("date")
    try:
        return datetime.datetime.strptime(date, "%Y%m%d")
    except (TypeError, ValueError):
        return None


class _SettlementObserver:
    """Wraps one week's allocator to observe keeks' settlement hook.

    :class:`keeks.allocation.AllocationSimulator` resolves ``update_bankroll`` and
    ``record_settlement`` on the allocation it is given, so this wrapper forwards
    ``evaluate`` to the caller's allocator (capturing the quoted weight vector) and
    receives the week's settlement (one outcome flag and one realized return per
    bet, keeks 0.9's unified hook contract) for the ledger. Online allocators'
    ``update_bankroll`` is forwarded so their state still tracks the run. It is
    deliberately duck-typed, mirroring the multi-outcome backtest's observer.
    """

    def __init__(self, allocator: BaseAllocationStrategy):
        self._allocator = allocator
        self.weights: Optional[Tuple[float, ...]] = None
        self.won: Optional[Tuple[bool, ...]] = None
        self.realized_returns: Optional[Tuple[float, ...]] = None

    def evaluate(self, current_bankroll: float) -> Any:
        weights = self._allocator.evaluate(current_bankroll)
        self.weights = tuple(weights)
        return weights

    def update_bankroll(self, total_funds: float) -> None:
        hook = getattr(self._allocator, "update_bankroll", None)
        if callable(hook):
            hook(total_funds)

    def record_settlement(self, won: Tuple[bool, ...], realized_returns: Tuple[float, ...]) -> None:
        self.won = tuple(won)
        self.realized_returns = tuple(realized_returns)


class WeeklyPortfolioBacktest:
    """Backtests rating-driven betting with each period's slate sized jointly.

    The run walks a period-keyed schedule in order. For each betting period it
    prices every bettable game against the ratings as they stand -- the period's
    own results are not yet rated, so nothing leaks -- builds the week's
    :class:`keeks.allocation.BinaryBetsModel`, asks the caller's allocator factory
    for an allocator over it, settles one :class:`keeks.allocation.AllocationSimulator`
    trial through the shared bankroll, and only then rates the period's recorded
    results. Periods up to and including ``period_to_start_betting`` are rating-only
    warm-up: their games rate but nothing is priced or staked in them.

    **One bet per game, winner side.** Each game contributes a single option: the
    recorded winner's side at its posted moneyline, sized by the arena's win
    probability for that team. The multi-outcome alternative -- also backing the
    loser side -- would put two perfectly anti-correlated options in a model whose
    correlation-aware allocators assume independence, so the slate stays one bet
    per game. (The per-bet engine's two-sided candidates are its own convention;
    see ``keeks_elote.backtest.Backtest``.)

    **An allocator per week.** The factory receives the week's model and returns
    the allocator that sizes it, because the slate's width changes from week to
    week -- games drop in and out with their moneylines -- and every shipped
    allocator fixes its weight-vector width at construction from that week's
    moments or scenarios. Stateful (online) allocators keep their state across
    weeks through the forwarded ``update_bankroll`` hook only when the factory
    returns the same instance each week; moment-based factories construct a fresh
    allocator per week, which is the common case.

    **One trial per week.** The simulator runs ``trials=1`` per week, so the
    bankroll's batch-net settlement convention evaluates exactly once per week:
    the week's stakes are ``bettable_funds * weight`` per bet, and the whole
    batch nets to a single bankroll transaction.

    **Seeding.** With ``seed`` set, week ``t`` of the schedule (in sorted period
    order, warm-up weeks included) settles from a simulator seeded ``seed + t`` --
    the per-stream pattern :mod:`keeks_elote.multi_outcome_backtest` uses per game
    -- so a seeded run replays bit-exactly, and changing ``period_to_start_betting``
    does not shift any week's stream. With ``seed=None`` the draws come from numpy's
    global generator and no replay is promised.

    **Time-stamped rating.** When every game in the schedule carries a parseable
    ``date`` (``"%Y%m%d"``), rating is time-stamped from those dates: a week is
    rated in kickoff order, and Glicko's rating-deviation decay follows the
    fixture's calendar instead of the wall clock. Without this, two runs of the
    same fixture disagree at the ~1e-11 level (microsecond timing between rating
    updates) and downstream value-keyed sampling inherits the drift -- a seeded
    replay would only be bit-exact within one process. Any undated game switches
    the whole run to elote's default wall-clock rating.

    :param arena: An initialized elote arena (e.g. from :func:`create_arena`).
    """

    def __init__(self, arena: RatingArena):
        """Initializes the weekly-portfolio backtest environment.

        :param arena: An initialized elote arena instance.
        """
        logger.info("Initializing WeeklyPortfolioBacktest with arena: %s", type(arena).__name__)
        self._arena = arena
        self.bet_history: List[Dict[str, Any]] = []

    def _rate_games(self, games: List[GameRecord], time_stamped: bool) -> None:
        """Rates a period's recorded results through the arena.

        With ``time_stamped`` (every game in the schedule dated), matchups carry
        the kickoff as elote's ``matchup(a, b, attributes, match_time)`` fourth
        element and rate in kickoff order -- elote rejects out-of-order match
        times. Without it, plain matchups rate on the arena's default clock.
        """
        matchups = [_matchup_tuple(game) for game in games]
        if time_stamped:
            # The mode scan guarantees every game parsed, so no ``None`` here.
            # ``match_time`` is the fourth element of the matchup tuple's shape.
            stamped: List[Tuple[datetime.datetime, MatchupTuple]] = []
            for matchup, game in zip(matchups, games):
                match_time = _match_time(game)
                stamped.append((match_time or datetime.datetime.min, (*matchup[:3], match_time, *matchup[4:])))
            stamped.sort(key=lambda pair: pair[0])
            matchups = [matchup for _, matchup in stamped]
        if matchups:
            logger.debug("Updating arena ratings with %d matchups.", len(matchups))
            self._arena.tournament(matchups)

    def run_explicit(
        self,
        data: Dict[int, List[GameRecord]],
        allocator_factory: AllocatorFactory,
        bankroll: BankRoll,
        transaction_cost_rate: float = 0.0,
        period_to_start_betting: int = 0,
        seed: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Runs the weekly-portfolio backtest, period by period.

        Per period, in order: price the period's bettable games against the ratings
        as they stand (betting periods only), settle the week's slate as one
        portfolio decision through the shared bankroll, then rate the period's
        recorded results. A week's ratings therefore reflect only prior weeks.

        :param data: Historical game data keyed by period; each game is a dict
                     satisfying the :class:`keeks_elote.types.GameRecord` schema --
                     ``winner``/``loser`` labels are required, ``winner_ml`` makes
                     the game bettable when it converts to a usable price.
        :param allocator_factory: Maps the week's
                                  :class:`keeks.allocation.BinaryBetsModel` to the
                                  allocator that sizes it (see the class docstring).
        :param bankroll: The keeks bankroll to bet from, updated in place.
        :param transaction_cost_rate: The per-unit-staked fee folded into every
                                      bet's win and loss returns in the week's
                                      model. Defaults to 0.0 (fee-free).
        :param period_to_start_betting: The last period that only builds ratings;
                                        real bets begin the period after it.
                                        Defaults to 0.
        :param seed: Base seed for the per-week settlement streams (see the class
                     docstring). ``None`` promises no replay.
        :return: The run's weekly ledger -- also stored on ``self.bet_history``
                 (cleared at the start of each call), one dict per settled week:

                 ``period``
                     Where the week sat in the schedule.
                 ``bets``
                     The slate: one entry per bet -- the backed label and its
                     opponent, the arena's win probability, and the decimal-odds
                     price -- in schedule order.
                 ``weights``
                     The allocator's weight vector over the slate, or ``None``
                     when the allocator raised before quoting one.
                 ``stakes`` / ``stake``
                     The per-bet stakes (``bettable_funds * weight``) and their
                     total, the denominator :func:`keeks_elote.backtest.roi` uses.
                 ``returns`` / ``won``
                     The settled per-bet simple returns (keeks'
                     ``record_settlement`` convention) and outcome flags, or
                     ``None`` when nothing settled; ``won`` is ``True`` when the
                     week's net profit is positive.
                 ``profit`` / ``bankroll_before`` / ``bankroll_after``
                     The week's net effect and the bankroll reads around it.
                     ``BankRoll`` reads are rounded to cents, so ``profit``
                     agrees with the exact ``returns`` accounting only to within
                     that cent. :func:`keeks_elote.backtest.pnl` and
                     :func:`keeks_elote.backtest.roi` consume these fields.
                 ``skipped_zero_stake`` / ``error``
                     Flags for weeks that moved no money: an allocator that
                     quoted all-zero weights, or an evaluation (or settlement)
                     that raised, with the error message recorded.
        """
        logger.info("Starting weekly-portfolio backtest run.")
        self.bet_history = []

        data = prepare_data(data)
        logger.debug("Prepared data keys (periods): %s", list(data.keys()))

        # Deterministic-replay mode: rate from the schedule's own calendar only
        # when every game is dated, so a run never mixes the two clocks.
        time_stamped = all(_match_time(game) is not None for games in data.values() for game in games)
        logger.debug("Time-stamped rating: %s.", time_stamped)

        history: List[Dict[str, Any]] = []
        for week_index, period in enumerate(sorted(data)):
            games = data[period]
            is_betting_period = period > period_to_start_betting
            # Per-week settlement stream: schedule position, warm-up weeks included,
            # so a week's stream is independent of where betting starts.
            week_seed = None if seed is None else seed + week_index

            if not is_betting_period:
                logger.debug("Period %s: warm-up week; rating only.", period)
                self._rate_games(games, time_stamped)
                continue

            slate = []
            for game in games:
                decimal_odds = _decimal_for_winner(game)
                if decimal_odds is None:
                    continue
                probability = calculate_probabilities(self._arena, game)
                slate.append(
                    {
                        "label": game.get("winner"),
                        "opponent": game.get("loser"),
                        "probability": probability,
                        "payoff": decimal_odds,
                    }
                )

            if not slate:
                logger.info("Period %s: no bettable games; rating only.", period)
                self._rate_games(games, time_stamped)
                continue

            model = BinaryBetsModel(
                [(bet["probability"], bet["payoff"], 1.0) for bet in slate],
                transaction_cost_rate=transaction_cost_rate,
            )
            allocator = allocator_factory(model)
            observer = _SettlementObserver(allocator)
            simulator = AllocationSimulator(model=model, trials=1, seed=week_seed)

            # Read before the trial: the simulator stakes from the bettable funds
            # as they stand when the trial begins, and nothing mutates the
            # bankroll between here and its settlement.
            bettable_funds = bankroll.bettable_funds
            bankroll_before = bankroll.total_funds
            error: Optional[str] = None
            try:
                simulator.evaluate_strategy(observer, bankroll)
            except Exception as exc:
                error = str(exc)
                logger.error("Error settling period %s's slate: %s", period, exc)

            weights = observer.weights
            realized = observer.realized_returns
            stakes = tuple(bettable_funds * weight for weight in weights) if weights is not None else ()
            profit = bankroll.total_funds - bankroll_before
            record: Dict[str, Any] = {
                "period": period,
                "bets": slate,
                "weights": weights,
                "stakes": stakes,
                "stake": float(sum(stakes)),
                "returns": realized,
                "won": profit > 0.0,
                "profit": profit,
                "bankroll_before": bankroll_before,
                "bankroll_after": bankroll.total_funds,
                "skipped_zero_stake": realized is None,
                "error": error,
            }
            history.append(record)
            self.bet_history.append(record)
            logger.info(
                "Period %s: %d bets, stakes %.2f, weights %s, profit %.2f, bankroll %.2f.",
                period,
                len(slate),
                record["stake"],
                weights,
                profit,
                bankroll.total_funds,
            )
            self._rate_games(games, time_stamped)  # Settle the week, then its results rate.

        logger.info("Weekly-portfolio run finished: %d weeks settled.", len(history))
        return history
