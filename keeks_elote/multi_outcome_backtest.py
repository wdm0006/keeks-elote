"""1X2 (home / draw / away) backtesting through keeks' multi-outcome API.

Where :class:`keeks_elote.backtest.Backtest` prices a single binary wager per
game, this module backtests the whole 1X2 book -- home, draw, and away legs --
with keeks' multi-outcome machinery:

* :func:`one_x_two_probabilities` expands the arena's rating-derived
  "no-draw" win probability into a full three-leg book, reserving a draw
  probability that peaks at rating parity (the Davidson tie term).
* :class:`MultiOutcomeBacktest` walks a period-keyed schedule, prices each
  game's book from the ratings as they stand, sizes the three stakes with
  :class:`keeks.multi_outcome.MultiOutcomeKellyCriterion`, and settles each
  game through a per-game
  :class:`keeks.multi_outcome.RepeatedMultiOutcomeSimulator` -- one trial, one
  categorical draw, exactly one leg realized.

Two semantics differ from the binary backtest and are worth naming:

* **Settlement is simulated, not recorded.** A categorical draw realizes one
  leg from the model's own probabilities; the recorded scores rate the
  competitors but never decide a settled bet. The binary backtest instead
  settles against the recorded result. Simulated settlement is what makes the
  flow a projection exercise -- it prices the strategy the model's own world.
* **``payoffs`` are decimal odds.** keeks' multi-outcome contract quotes each
  leg's payoff as decimal odds -- a winning leg pays ``payoff * stake``, stake
  included -- while the binary backtest's ledger records ``payoff`` as decimal
  odds minus one. The same word means different things one module away; this
  module's ledger uses the multi-outcome convention.

Rating updates treat a draw as a draw: elote arenas receive the recorded
result as ``outcome`` 1.0 / 0.0 / 0.5 from the home perspective, with the
score pair elote cross-checks it against.

This module is also where the Phase 3 load-bearing assumption -- keeks-elote
call sites can consume the multi-outcome API -- is exercised for real
(Phase 3 execution spec, deliverable K4). It needs ``keeks.multi_outcome``,
which first ships in keeks 0.8.0; until that release is on PyPI, install keeks
from its git default branch (``make install`` does).
"""

import inspect
import logging
import numbers
from typing import Any, Dict, List, Optional, Tuple, cast

from keeks.bankroll import BankRoll
from keeks.multi_outcome import BaseMultiOutcomeStrategy, RepeatedMultiOutcomeSimulator

from keeks_elote.backtest import to_decimal
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import MatchupTuple, OneXTwoGameRecord

logger = logging.getLogger(__name__)

#: Leg order used everywhere: the positional index of a probability, payoff,
#: stake fraction, or settlement return is fixed by this tuple.
LEGS = ("home", "draw", "away")


def _require_unit_interval(value: Any, name: str) -> float:
    """Validates one probability-like argument and returns it as a float."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise TypeError(f"{name} must be a real number, got {value!r}")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be within [0, 1], got {number!r}")
    return number


def one_x_two_probabilities(p_home: float, draw_rate: float = 0.25) -> Tuple[float, float, float]:
    """Builds a 1X2 book from a rating-derived, draw-blind win probability.

    elote arenas score a pair of competitors symmetrically -- a single
    "expected score" with no third outcome -- so the 1X2 third leg has to be
    modeled. The draw probability follows the Davidson tie term,
    ``draw_rate * 4 * p * (1 - p)``, which peaks at ``draw_rate`` when the two
    sides are rated evenly and fades toward the extremes (favorites draw
    less); the remaining mass is split in proportion to the original win
    probability. The three returned probabilities always sum to one, so a
    fully priced 1X2 book leaves no void mass on which the market refunds.

    :param p_home: The arena's expected score for the home side -- the
                   probability the home team beats the away team in the
                   arena's draw-blind view, in ``[0, 1]``.
    :param draw_rate: The model's draw probability at rating parity, in
                      ``[0, 1]``. Roughly a quarter is typical for association
                      football; the default is ``0.25``.
    :return: The (home, draw, away) probability book, in :data:`LEGS` order,
             summing to one.
    :raises TypeError: If either argument is not a real number.
    :raises ValueError: If either argument falls outside ``[0, 1]``.
    """
    probability = _require_unit_interval(p_home, "p_home")
    rate = _require_unit_interval(draw_rate, "draw_rate")

    p_draw = rate * 4.0 * probability * (1.0 - probability)
    remaining = 1.0 - p_draw
    return (remaining * probability, p_draw, remaining * (1.0 - probability))


def _one_x_two_matchup(game: OneXTwoGameRecord) -> Optional[Tuple[Any, Any, None, None, float, Tuple[float, float]]]:
    """Builds the arena matchup tuple for a settled 1X2 game, draws included.

    The outcome is the recorded result from the home perspective -- 1.0 home
    win, 0.0 away win, 0.5 draw -- and the score pair rides along in
    ``(home_score, away_score)`` order, the convention elote cross-checks the
    outcome against (a 0.5 outcome must carry equal scores, which this
    construction guarantees). ``None`` means the record lacks a usable result
    and must not be rated; the caller warns and skips.
    """
    home, away = game.get("home"), game.get("away")
    home_score, away_score = game.get("home_score"), game.get("away_score")
    if home is None or away is None or home_score is None or away_score is None:
        return None
    try:
        scores = (float(home_score), float(away_score))
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparseable scores %r/%r for %s vs %s.",
            home_score,
            away_score,
            home,
            away,
        )
        return None
    if scores[0] > scores[1]:
        outcome = 1.0
    elif scores[0] < scores[1]:
        outcome = 0.0
    else:
        outcome = 0.5
    return (home, away, None, None, outcome, scores)


def _game_payoffs(game: OneXTwoGameRecord) -> Optional[Tuple[float, float, float]]:
    """Reads the game's three prices as decimal odds, in :data:`LEGS` order.

    Each price goes through :func:`keeks_elote.backtest.to_decimal`, so either
    odds format is accepted per value. ``None`` means the game is not bettable:
    either a leg has no price at all (debug -- unpriced games are normal) or a
    price that fits no format (warning, mirroring the binary backtest).
    """
    home, away = game.get("home"), game.get("away")
    payoffs: List[float] = []
    for odds_key, leg in zip(("home_odds", "draw_odds", "away_odds"), LEGS):
        odds = game.get(odds_key)
        if odds is None:
            logger.debug("Skipping 1X2 bets on %s vs %s: no %s price.", home, away, leg)
            return None
        try:
            payoffs.append(to_decimal(odds))
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping 1X2 bets on %s vs %s: invalid %s odds %r: %s", home, away, leg, odds, exc)
            return None
    return (payoffs[0], payoffs[1], payoffs[2])


def _reprice_for_game(
    strategy: BaseMultiOutcomeStrategy, payoffs: Tuple[float, float, float]
) -> BaseMultiOutcomeStrategy:
    """Returns the strategy instance to price one game's book with.

    Multi-outcome strategies fix their payoffs at construction and reprice by
    fresh construction (the pattern the binary backtest established in PR #50),
    so an ABC strategy is rebuilt per game with the game's decimal payoffs and
    its other constructor arguments replayed from same-named attributes. When
    the type does not follow that contract (or a required argument was never
    stored), the original instance is returned as-is: the simulator's own odds
    check then rejects it with a precise error, which the run records as a
    failed evaluation. Duck-typed strategies (anything outside
    ``BaseMultiOutcomeStrategy``) are always passed through -- they carry no
    payoffs contract to reprice, and their odds compatibility is the caller's
    responsibility, matching the simulator's own stance.
    """
    if not isinstance(strategy, BaseMultiOutcomeStrategy):
        return strategy

    try:
        parameters = inspect.signature(type(strategy).__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - opaque C-level initializers
        return strategy

    kwargs: Dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            return strategy
        if name == "self":
            continue
        if name == "payoffs":
            kwargs[name] = payoffs
            continue
        value = getattr(strategy, name, parameter.default)
        if value is inspect.Parameter.empty:
            # A required constructor argument the instance never stored cannot be
            # replayed (nothing in keeks ships one today); let the simulator's
            # odds check name the mismatch instead of guessing a value.
            logger.warning(
                "Strategy %s does not expose constructor argument %r; pricing this game with the "
                "strategy's own configured odds instead.",
                type(strategy).__name__,
                name,
            )
            return strategy
        kwargs[name] = value
    if "payoffs" not in kwargs:
        return strategy
    return type(strategy)(**kwargs)


def _validated_record(game: Any) -> Optional[OneXTwoGameRecord]:
    """Validates one raw game record against the 1X2 schema, warning on failures.

    The schedule boundary is untyped (``List[Any]`` from user data), so the
    record is checked here once and narrowed to :class:`OneXTwoGameRecord`
    for both the settlement and rating paths; anything that cannot be rated
    is warned about and skipped.
    """
    if not isinstance(game, dict):
        logger.warning("Skipping non-dict game record %r.", game)
        return None
    if game.get("home") is None or game.get("away") is None:
        logger.warning("Dropping game with missing home/away labels: %r", game)
        return None
    if _one_x_two_matchup(cast(OneXTwoGameRecord, game)) is None:
        logger.warning(
            "Skipping %r vs %r -- no usable recorded result to rate.",
            game.get("home"),
            game.get("away"),
        )
        return None
    return cast(OneXTwoGameRecord, game)


class _SettlementObserver:
    """Wraps one game's pricing strategy to observe keeks' settlement hooks.

    keeks' simulators look their hooks up on the strategy they are given, so
    this wrapper receives ``update_bankroll`` and ``record_settlement`` once
    per trial, records the settlement for the ledger, and forwards both to the
    caller's strategy when it exposes them -- stateful strategies update on
    the instance the caller passed, mirroring the binary backtest's
    notification rule. It is deliberately duck-typed: the simulator only
    odds-checks ``BaseMultiOutcomeStrategy`` instances, and the pricing
    strategy it wraps has already been reconciled with the game's odds.
    """

    def __init__(self, pricing_strategy: Any, caller_strategy: Any):
        self._pricing_strategy = pricing_strategy
        self._caller_strategy = caller_strategy
        self.fractions: Optional[Tuple[float, ...]] = None
        self.won_leg: Optional[int] = None
        self.return_pcts: Optional[Tuple[float, ...]] = None

    def evaluate(self, probabilities: Any, current_bankroll: float) -> Any:
        fractions = self._pricing_strategy.evaluate(probabilities, current_bankroll)
        self.fractions = tuple(fractions)
        return fractions

    def _forward(self, hook_name: str, *args: Any) -> None:
        hook = getattr(self._caller_strategy, hook_name, None)
        if not callable(hook):
            return
        try:
            hook(*args)
        except Exception:
            logger.exception(
                "Strategy %s raised from %s; continuing without the state update.",
                type(self._caller_strategy).__name__,
                hook_name,
            )

    def update_bankroll(self, total_funds: float) -> None:
        self._forward("update_bankroll", total_funds)

    def record_settlement(self, won_leg: Optional[int], return_pcts: Tuple[float, ...]) -> None:
        self.won_leg = won_leg
        self.return_pcts = tuple(return_pcts)
        self._forward("record_settlement", won_leg, self.return_pcts)


class MultiOutcomeBacktest:
    """Backtests 1X2 (home / draw / away) betting through keeks' multi-outcome API.

    The run walks a period-keyed schedule in order. For each period it prices
    every game's book against the ratings as they stand (the period's own
    results are not yet rated, so nothing leaks), sizes the three stakes, and
    settles each game through its own one-trial
    :class:`keeks.multi_outcome.RepeatedMultiOutcomeSimulator`; only then does
    it rate the period's recorded results, draws included.

    Each game carries its own probability book and its own prices, so each
    game gets a freshly constructed strategy (per-game repricing) and its own
    simulator instance seeded ``seed + game_index`` in schedule order -- the
    per-stream pattern keeks' simulators document. With ``seed=None`` the
    draws come from numpy's global generator and no replay is promised.

    :param arena: An initialized elote arena (e.g. from :func:`create_arena`).
    :param draw_rate: The draw probability the pricing model assumes at rating
                      parity; see :func:`one_x_two_probabilities`.

    **The ledger.** Every game the run considered is recorded on
    ``bet_history`` (cleared at the start of each run), one dict per game:

    ``period`` / ``home`` / ``away``
        Where the game sat in the schedule and who played it.
    ``probabilities`` / ``payoffs``
        The model's (home, draw, away) book and the game's decimal-odds
        prices, in :data:`LEGS` order.
    ``fractions``
        The stake fraction quoted per leg, or ``None`` when the strategy
        raised before quoting one.
    ``stakes``
        The absolute amount staked per leg -- the quoted fractions scaled by
        the bankroll's bettable funds at the trial's start.
    ``stake``
        The game's total stake across legs; the denominator :func:`roi` uses.
    ``won_leg``
        The realized leg's index, or ``None`` for a void round or a game that
        settled nothing. A fully priced book (this module's books always are)
        settles exactly one leg per staked trial.
    ``returns``
        The signed net return per leg as a fraction of the bankroll before the
        trial, keeks' ``record_settlement`` convention; 0.0 for legs that
        settled nothing.
    ``profit`` / ``bankroll_before`` / ``bankroll_after``
        The settlement's net effect and the bankroll reads around it.
        ``BankRoll`` reads are rounded to cents, so ``profit`` agrees with
        the exact settlement ``returns`` only to within that cent.
        :func:`pnl` and :func:`roi` consume these fields directly.
    ``skipped_zero_stake`` / ``error``
        Flags for the games that moved no money: a strategy that declined
        every leg, or an evaluation (or settlement) that raised, with the
        error message recorded.

    Games that cannot be rated (missing labels or scores) or cannot be priced
    (a leg with no price, or a price that fits no format) are warned about and
    skipped: they produce no ledger entry and, when unratable, no rating
    update either.
    """

    def __init__(self, arena: RatingArena, draw_rate: float = 0.25):
        """Initializes the 1X2 backtest environment.

        :param arena: An initialized elote arena instance.
        :param draw_rate: The draw probability at rating parity, in ``[0, 1]``.
        """
        logger.info("Initializing MultiOutcomeBacktest with arena: %s", type(arena).__name__)
        # Fail fast on a draw rate the pricing model cannot use, rather than on
        # the first game of a run hours into a schedule.
        self._draw_rate = _require_unit_interval(draw_rate, "draw_rate")
        self._arena = arena
        self.bet_history: List[Dict[str, Any]] = []

    def _book_for_game(self, game: OneXTwoGameRecord) -> Tuple[float, float, float]:
        """Prices a game's 1X2 book from the arena's current ratings."""
        p_home = self._arena.expected_score(game["home"], game["away"])
        return one_x_two_probabilities(p_home, self._draw_rate)

    def _settle_game(
        self,
        game: OneXTwoGameRecord,
        strategy: BaseMultiOutcomeStrategy,
        bankroll: BankRoll,
        period: int,
        game_seed: Optional[int],
    ) -> None:
        """Prices and settles one game, appending its ledger entry."""
        home, away = game["home"], game["away"]
        book = self._book_for_game(game)
        payoffs = _game_payoffs(game)
        if payoffs is None:
            # Rated below like every other game; just not bettable.
            return

        record: Dict[str, Any] = {
            "period": period,
            "home": home,
            "away": away,
            "probabilities": book,
            "payoffs": payoffs,
            "fractions": None,
            "stakes": (0.0, 0.0, 0.0),
            "stake": 0.0,
            "won_leg": None,
            "returns": (0.0, 0.0, 0.0),
            "profit": 0.0,
            "bankroll_before": bankroll.total_funds,
            "bankroll_after": bankroll.total_funds,
            "skipped_zero_stake": False,
            "error": None,
        }
        self.bet_history.append(record)

        simulator = RepeatedMultiOutcomeSimulator(
            payoffs=payoffs,
            loss=1.0,
            transaction_costs=0.0,
            probabilities=book,
            trials=1,
            seed=game_seed,
        )
        observer = _SettlementObserver(_reprice_for_game(strategy, payoffs), strategy)

        # Read before the trial: the simulator stakes from the bettable funds
        # as they stand when the trial begins, and nothing mutates the
        # bankroll between here and the stake sizing inside evaluate_strategy.
        bettable_funds = bankroll.bettable_funds
        try:
            simulator.evaluate_strategy(observer, bankroll)
        except Exception as exc:
            record["error"] = str(exc)
            logger.error("Error settling 1X2 game %s vs %s: %s", home, away, exc)
            return

        record["fractions"] = observer.fractions
        record["won_leg"] = observer.won_leg
        if observer.return_pcts is not None:
            record["returns"] = observer.return_pcts
        else:
            # No settlement hook fired: the strategy staked nothing, so the
            # simulator skipped the trial entirely (no draw, no fee).
            record["skipped_zero_stake"] = True
        record["stakes"] = tuple(
            (fraction or 0.0) * bettable_funds for fraction in (record["fractions"] or (0.0, 0.0, 0.0))
        )
        record["stake"] = float(sum(record["stakes"]))
        record["bankroll_after"] = bankroll.total_funds
        record["profit"] = record["bankroll_after"] - record["bankroll_before"]
        logger.debug(
            "1X2 %s vs %s: book (%.3f, %.3f, %.3f), fractions (%.4f, %.4f, %.4f), won leg %s, profit %.2f.",
            home,
            away,
            *book,
            *(record["fractions"] or (0.0, 0.0, 0.0)),
            record["won_leg"],
            record["profit"],
        )

    def run_explicit(
        self,
        data: Dict[int, List[Any]],
        strategy: BaseMultiOutcomeStrategy,
        bankroll: BankRoll,
        period_to_start_betting: int = 3,
        seed: Optional[int] = None,
    ) -> BankRoll:
        """Runs the 1X2 backtest, period by period.

        Per period, in order: price and settle every game against the ratings
        as they stand (when the period is a betting period), then rate the
        period's recorded results -- wins, losses, and draws -- through the
        arena. Periods up to and including ``period_to_start_betting`` are
        rating-only warm-up: nothing is priced or staked in them.

        :param data: Historical 1X2 game data keyed by period; each game is a
                     dict satisfying the :class:`OneXTwoGameRecord` schema --
                     ``home``/``away`` labels and ``home_score``/``away_score``
                     are required, the three odds keys are optional and make
                     the game bettable when present.
        :param strategy: The multi-outcome strategy to size stakes with. ABC
                         strategies are repriced per game by fresh
                         construction; stateful strategies receive
                         ``update_bankroll`` and ``record_settlement`` on the
                         instance passed in, once per settled game.
        :param bankroll: The keeks bankroll to bet from, updated in place.
        :param period_to_start_betting: The last period that only builds
                                        ratings; real bets begin the period
                                        after it. Defaults to 3.
        :param seed: Base seed for the per-game settlement streams. Each
                     game's simulator is seeded ``seed + game_index`` in
                     schedule order, so a seeded run replays identically.
        :return: The bankroll, updated with the run's settlements.
        """
        logger.info("Starting 1X2 backtest run.")
        self.bet_history = []

        if not isinstance(data, dict):
            raise TypeError(f"Expected a dict keyed by period, got {type(data).__name__}.")

        game_index = 0
        for period in sorted(data):
            games = data[period]
            if not isinstance(games, list):
                raise TypeError(f"Period {period} should contain a list of games, got {type(games).__name__}.")

            is_betting_period = period > period_to_start_betting

            # --- Price and settle this period's games (ratings exclude them so far) ---
            rated_games: List[OneXTwoGameRecord] = []
            for game in games:
                record = _validated_record(game)
                if record is None:
                    game_index += 1
                    continue
                rated_games.append(record)
                if is_betting_period:
                    game_seed = seed + game_index if seed is not None else None
                    self._settle_game(record, strategy, bankroll, period, game_seed)
                else:
                    logger.debug(
                        "Period %s: warm-up; %s vs %s is rated but not bet.",
                        period,
                        record["home"],
                        record["away"],
                    )
                game_index += 1

            # --- Rate this period's recorded results (draws included) ---
            matchups: List[MatchupTuple] = []
            for record in rated_games:
                # Validation already screened every record through the same
                # check, so the None branch is unreachable at runtime.
                matchup = _one_x_two_matchup(record)
                if matchup is not None:
                    matchups.append(matchup)
            if matchups:
                logger.info("Updating arena ratings with %d results from period %s.", len(matchups), period)
                self._arena.tournament(matchups)

        summary_placed = sum(1 for record in self.bet_history if record["stake"] > 0 and record["error"] is None)
        summary_failed = sum(1 for record in self.bet_history if record["error"] is not None)
        logger.info(
            "1X2 backtest run finished: %d games staked, %d failed. Final bankroll: %.2f",
            summary_placed,
            summary_failed,
            bankroll.total_funds,
        )
        return bankroll
