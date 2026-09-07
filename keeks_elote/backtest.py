import copy
import inspect
import logging
import math
import numbers
from collections import Counter
from typing import Any, Dict, List, Optional, Set

from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote.data_handling import prepare_data
from keeks_elote.model_evaluation import calculate_probabilities
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord, MatchupTuple, ProjectionRecord

logger = logging.getLogger(__name__)


# Helper to convert American odds to decimal odds
def _matchup_tuple(game: GameRecord) -> MatchupTuple:
    """Builds the arena matchup tuple for a settled game, pinning the recorded result.

    The record names the winner, so the outcome is always forwarded as ``1.0`` from the
    first competitor's perspective: the arena's comparison function predicts rather than
    records, and a non-trivial one must never decide ground truth for a game that has a
    recorded winner. Rating systems that model margin of victory (Massey, Keener,
    Pythagorean) additionally need the scores, so a game carrying a usable
    ``winner_score`` > ``loser_score`` is forwarded with them; elote's ``tournament``
    unpacks each tuple into ``matchup``, whose signature is
    ``(a, b, attributes, match_time, outcome, scores)``, and cross-checks the scores
    against the outcome. That signature requires elote >= 1.3.0, the declared floor:
    1.2.x has no way to receive a recorded result at all. A record with no
    winner/loser labels carries no result to forward, so it falls back to the
    two-element comparison-function form (warned, and unreachable after
    ``prepare_data``, which drops such games).
    """
    winner, loser = game.get("winner"), game.get("loser")
    if winner is None or loser is None:
        logger.warning(
            "Game record %r carries no recorded result; deferring to the arena's comparison function.",
            game,
        )
        return (winner, loser)

    winner_score, loser_score = game.get("winner_score"), game.get("loser_score")
    if winner_score is None or loser_score is None:
        return (winner, loser, None, None, 1.0)
    try:
        scores = (float(winner_score), float(loser_score))
    except (TypeError, ValueError):
        logger.warning(
            "Ignoring unparseable scores %r/%r for %s over %s.",
            winner_score,
            loser_score,
            winner,
            loser,
        )
        return (winner, loser, None, None, 1.0)
    if not scores[0] > scores[1]:
        # The row says this competitor won but the scores do not agree. A placeholder like
        # "0-0" for a score nobody recorded is the common case, and feeding it through as a
        # real margin would tell a margin-aware system the game was a tie. Rate it on the
        # recorded result alone rather than dropping the game or failing the run.
        logger.warning(
            "Scores %s do not show %s beating %s; rating this game on its result alone.",
            scores,
            winner,
            loser,
        )
        return (winner, loser, None, None, 1.0)

    # Outcome is from the first competitor's perspective, and the first competitor is the
    # winner, so this is always 1.0. elote requires it alongside scores and cross-checks
    # the two for agreement.
    return (winner, loser, None, None, 1.0, scores)


def american_to_decimal(american_odds: Any) -> float:
    """Converts numeric American odds to decimal odds.

    :param american_odds: A finite, non-zero real number. Booleans, numeric
                          strings and other non-real values are rejected rather
                          than converted.
    :raises TypeError: If the value is not a real number.
    :raises ValueError: If the value is zero or non-finite.
    :return: The equivalent decimal odds.
    :rtype: float
    """
    if isinstance(american_odds, bool) or not isinstance(american_odds, numbers.Real):
        raise TypeError(f"American odds must be a real number, got {american_odds!r}")

    try:
        odds = float(american_odds)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"American odds must be representable as a float, got {american_odds!r}") from exc

    if not math.isfinite(odds):
        raise ValueError(f"American odds must be finite, got {american_odds!r}")
    if odds == 0:
        raise ValueError(f"American odds must be non-zero, got {american_odds!r}")

    if odds > 0:
        return (odds / 100.0) + 1.0
    else:
        return (100.0 / abs(odds)) + 1.0


def _decimal_odds_for_side(american_odds: Any, label: Any) -> Optional[float]:
    """Converts one side's odds, warning and returning ``None`` when they are invalid."""
    try:
        return american_to_decimal(american_odds)
    except (TypeError, ValueError) as exc:
        logger.warning(f"Skipping wager on {label} due to invalid odds {american_odds!r}: {exc}")
        return None


# Strategy types already warned about when a re-price fell back to a copy; one warning
# per type keeps a long backtest from repeating the same diagnosis on every bet.
_copy_fallback_warned: Set[type] = set()


def _reprice_by_construction(strategy: BaseStrategy, payoff: float, loss: float) -> Optional[BaseStrategy]:
    """Builds a fresh strategy of the same type carrying the bet's pricing, or ``None``.

    keeks strategies are immutable after init, so re-pricing a bet must never write
    attributes on a (copied) instance; a new one is constructed through the real
    constructor instead. keeks strategies store every constructor argument under a
    same-named attribute, so the other arguments are read back off the instance and
    replayed through ``__init__``. ``None`` means the type does not follow that
    contract and cannot be faithfully reconstructed.
    """
    try:
        parameters = inspect.signature(type(strategy).__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - opaque C-level initializers
        return None

    kwargs: Dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            return None
        if name == "self":
            continue
        if name == "payoff":
            kwargs[name] = payoff
        elif name == "loss":
            kwargs[name] = loss
        else:
            value = getattr(strategy, name, parameter.default)
            if value is inspect.Parameter.empty:
                # A required constructor argument the instance never stored cannot be
                # replayed; its original value is unknowable. CPPI's initial_bankroll,
                # which is consumed into the floor at init, is the shipped example.
                return None
            kwargs[name] = value
    if "payoff" not in kwargs or "loss" not in kwargs:
        # The constructor does not accept the bet's pricing, so a fresh instance
        # would silently quote the strategy's own configured pricing instead.
        return None
    return type(strategy)(**kwargs)


def _strategy_for_bet(strategy: BaseStrategy, payoff: float, price_bets_at_true_odds: bool) -> BaseStrategy:
    """Returns the strategy instance to quote a single bet with.

    With ``price_bets_at_true_odds`` the bet is quoted a freshly constructed strategy
    re-priced for the game (the bet's payoff, full-stake loss) and the caller's
    strategy is left untouched. Without it, the strategy itself is passed through so
    it prices from its own configuration.
    """
    if not price_bets_at_true_odds:
        return strategy

    repriced = _reprice_by_construction(strategy, payoff, 1.0)
    if repriced is not None:
        return repriced

    # Strategies outside the keeks constructor contract (test doubles, custom
    # subclasses with their own initializers) cannot be re-priced by construction,
    # so their quotes fall back to the historical copied instance. That copy only
    # re-prices strategies that read the copied attributes; on a keeks version that
    # forbids attribute writes it fails loudly per bet rather than silently sizing
    # stakes from stale prices.
    if type(strategy) not in _copy_fallback_warned:
        _copy_fallback_warned.add(type(strategy))
        logger.warning(
            "Strategy %s does not follow the keeks constructor contract (every argument "
            "stored as a same-named attribute); quoting this bet from a copied instance "
            "instead of a freshly constructed one.",
            type(strategy).__name__,
        )
    bet_strategy = copy.copy(strategy)
    bet_strategy.payoff = payoff
    bet_strategy.loss = 1.0
    return bet_strategy


def _record_result_on_strategy(
    strategy: BaseStrategy,
    won: bool,
    profit: float,
    bankroll_before: float,
) -> None:
    """Notifies a stateful strategy of a settled bet, mirroring keeks' own simulators.

    keeks strategies may expose ``record_result(won, return_pct)`` to keep state between
    bets (DynamicBankrollManagement's streak and volatility windows, for example);
    strategies without the hook are skipped. ``return_pct`` follows the simulators'
    convention -- the bet's net profit over the bankroll it was placed from -- because a
    re-priced bet's economics differ from the strategy's configured pricing. A hook that
    raises is logged and skipped: the bet's money has already settled truthfully, and
    one broken state hook should not corrupt the financial record or abort the run.
    """
    hook = getattr(strategy, "record_result", None)
    if not callable(hook):
        return
    try:
        hook(won, profit / bankroll_before if bankroll_before > 0 else 0.0)
    except Exception:
        logger.exception(
            "Strategy %s raised from record_result; continuing without the state update.",
            type(strategy).__name__,
        )


def summarize_bet_history(bet_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarizes a bet history into the counts a run summary reports.

    Pure function over the record schema ``run_explicit`` documents, so the summary
    and any caller-side aggregation agree on the definitions: a placed bet moved
    money and settled; a failed bet is any candidate with an ``error`` (an evaluation
    the strategy could not price, or a settlement that raised); a skipped candidate
    quoted a stake that scaled or clamped to zero. Failure reasons are counted by
    error message, in first-seen order.
    """
    placed = [record for record in bet_history if record["stake"] > 0 and record["error"] is None]
    failed = [record for record in bet_history if record["error"] is not None]
    skipped = [record for record in bet_history if record["skipped_zero_stake"] and record["error"] is None]
    failure_reasons = Counter(record["error"] for record in failed)
    return {
        "total_candidates": len(bet_history),
        "placed_bets": len(placed),
        "failed_bets": len(failed),
        "failure_reasons": dict(failure_reasons),
        "skipped_zero_stake": len(skipped),
        "wins": sum(1 for record in placed if record["won"]),
        "losses": sum(1 for record in placed if not record["won"]),
        "net_profit": float(sum(record["profit"] for record in bet_history)),
    }


class Backtest:
    """Runs backtests for betting strategies using an elote Arena for ratings.

    This class orchestrates the process of simulating historical periods (e.g., weeks),
    updating competitor ratings based on outcomes, generating betting opportunities
    for future periods, and evaluating a given betting strategy against those
    opportunities.

    The strategy and bankroll are supplied separately when running a betting
    simulation.

    :param arena: An initialized elote Arena instance (e.g., GlickoArena).
    :type arena: RatingArena
    """

    def __init__(self, arena: RatingArena):
        """Initializes the Backtest environment.

        :param arena: An initialized elote Arena instance.
        :type arena: RatingArena
        """
        logger.info(f"Initializing Backtest with arena: {type(arena).__name__}")
        self._arena = arena
        self.bet_history: List[Dict[str, Any]] = []

    def _evaluate_bets_for_next_period(
        self,
        strategy: BaseStrategy,
        bankroll: BankRoll,
        next_period_games: List[GameRecord],
        price_bets_at_true_odds: bool,
        next_period_number: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Evaluates potential bets for a given list of games.

        Candidates the strategy cannot price are recorded on ``bet_history`` as
        failed evaluations (see :meth:`_record_failed_evaluation`) rather than
        vanishing behind a log line; ``next_period_number`` names the period the
        candidates would have settled in.
        """
        bets_calculated = []
        logger.debug(f"Evaluating {len(next_period_games)} games for betting opportunities.")
        for game in next_period_games:
            if "winner_odds" in game and "loser_odds" in game:
                winner_label = game.get("winner")
                loser_label = game.get("loser")
                winner_odds_american = game.get("winner_odds")
                loser_odds_american = game.get("loser_odds")

                if winner_label is None or loser_label is None:
                    logger.warning(f"Skipping game due to missing labels: {game}")
                    continue

                logger.debug(f"Evaluating game: {winner_label} vs {loser_label}")
                prob_winner_wins = calculate_probabilities(self._arena, game)
                prob_loser_wins = 1.0 - prob_winner_wins

                # Evaluate betting on the nominal winner
                decimal_odds_winner = (
                    _decimal_odds_for_side(winner_odds_american, winner_label)
                    if winner_odds_american is not None
                    else None
                )
                if decimal_odds_winner is not None:
                    try:
                        bet_strategy = _strategy_for_bet(
                            strategy,
                            decimal_odds_winner - 1.0,
                            price_bets_at_true_odds,
                        )
                        bet_fraction_winner = bet_strategy.evaluate(
                            probability=prob_winner_wins, current_bankroll=bankroll.total_funds
                        )
                        logger.debug(
                            f"Strategy suggests betting fraction {bet_fraction_winner:.4f} on {winner_label} (P={prob_winner_wins:.4f}, Odds={decimal_odds_winner:.2f})"
                        )
                        if bet_fraction_winner > 0:
                            bets_calculated.append(
                                {
                                    "label": winner_label,
                                    "opponent": loser_label,
                                    "fraction": bet_fraction_winner,
                                    "payoff": decimal_odds_winner - 1.0,
                                    "loss": 1.0,
                                    "actual_outcome": True,
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error evaluating bet on {winner_label}: {e}")
                        self._record_failed_evaluation(
                            period=next_period_number,
                            label=winner_label,
                            opponent=loser_label,
                            payoff=decimal_odds_winner - 1.0,
                            would_win=True,
                            error_message=str(e),
                            bankroll=bankroll,
                        )

                # Evaluate betting on the nominal loser
                decimal_odds_loser = (
                    _decimal_odds_for_side(loser_odds_american, loser_label)
                    if loser_odds_american is not None
                    else None
                )
                if decimal_odds_loser is not None:
                    try:
                        bet_strategy = _strategy_for_bet(
                            strategy,
                            decimal_odds_loser - 1.0,
                            price_bets_at_true_odds,
                        )
                        bet_fraction_loser = bet_strategy.evaluate(
                            probability=prob_loser_wins, current_bankroll=bankroll.total_funds
                        )
                        logger.debug(
                            f"Strategy suggests betting fraction {bet_fraction_loser:.4f} on {loser_label} (P={prob_loser_wins:.4f}, Odds={decimal_odds_loser:.2f})"
                        )
                        if bet_fraction_loser > 0:
                            bets_calculated.append(
                                {
                                    "label": loser_label,
                                    "opponent": winner_label,
                                    "fraction": bet_fraction_loser,
                                    "payoff": decimal_odds_loser - 1.0,
                                    "loss": 1.0,
                                    "actual_outcome": False,
                                }
                            )
                    except Exception as e:
                        logger.error(f"Error evaluating bet on {loser_label}: {e}")
                        self._record_failed_evaluation(
                            period=next_period_number,
                            label=loser_label,
                            opponent=winner_label,
                            payoff=decimal_odds_loser - 1.0,
                            would_win=False,
                            error_message=str(e),
                            bankroll=bankroll,
                        )
            else:
                logger.debug(
                    f"Skipping game {game.get('winner')} vs {game.get('loser')} for opportunities (missing odds or labels)."
                )
        return bets_calculated

    def _record_failed_evaluation(
        self,
        period: Optional[int],
        label: Any,
        opponent: Any,
        payoff: float,
        would_win: bool,
        error_message: str,
        bankroll: BankRoll,
    ) -> None:
        """Records a candidate the strategy could not price, next to the settled bets.

        Failed evaluations join ``bet_history`` with ``fraction`` of ``None`` (no
        stake was ever quoted) and the error message, so a strategy that raises on
        every bet leaves a ledger of failures and a ``failed_bets`` count in the run
        summary instead of an empty, plausible-looking run. The record is kept even
        when the candidate's period is not a betting period: the failure is a
        property of the strategy, not of the schedule.
        """
        self.bet_history.append(
            {
                "period": period,
                "label": label,
                "opponent": opponent,
                "fraction": None,
                "stake": 0.0,
                "payoff": payoff,
                "won": would_win,
                "profit": 0.0,
                "bankroll_after": bankroll.total_funds,
                "skipped_zero_stake": False,
                "error": error_message,
            }
        )

    def _execute_bets_for_current_period(
        self,
        strategy: BaseStrategy,
        bankroll: BankRoll,
        bets_to_execute: List[Dict[str, Any]],
        period_number: int,
    ) -> None:
        """Executes a list of bets against the provided bankroll.

        Every bet is sized as ``opening_funds * fraction``, the same base the
        strategy was quoted against, so wagers inside a period do not compound
        off each other.

        After a bet settles with money on it, strategies exposing keeks'
        ``record_result`` hook are notified via :func:`_record_result_on_strategy`.

        ``percent_bettable`` is a cap on the period's *total* exposure, not on
        each bet in isolation. A strategy quoting a fraction per game has no way
        to know how many other games it is being asked about, so a week of
        twenty confident bets routinely asks to stake several times the
        bankroll. When the period's requested stakes exceed the budget they are
        scaled down proportionally, which preserves the relative sizing the
        strategy asked for while keeping the total within the cap. Clamping each
        bet against the live funds instead would let the earliest games in a
        period consume the whole bankroll and starve the rest.
        """
        logger.info(f"Period {period_number}: Executing {len(bets_to_execute)} bets calculated previously.")
        opening_funds = bankroll.total_funds
        exposure_budget = bankroll.bettable_funds
        requested = sum(opening_funds * bet["fraction"] for bet in bets_to_execute if bet["fraction"] > 0)

        exposure_scale = 1.0
        if requested > exposure_budget and requested > 0:
            exposure_scale = exposure_budget / requested
            logger.warning(
                f"Period {period_number}: {len(bets_to_execute)} bets request {requested:.2f} "
                f"({requested / opening_funds:.1%} of the bankroll) against a bettable budget of "
                f"{exposure_budget:.2f}; scaling every stake by {exposure_scale:.4f}."
            )

        for bet in bets_to_execute:
            # Recorded after scaling and clamping, so the record always carries the amount
            # that reached bankroll.bet() rather than the amount the strategy asked for.
            stake = 0.0
            profit = 0.0
            bankroll_before = 0.0
            skipped_zero_stake = False
            error: Optional[str] = None
            try:
                bet_amount = opening_funds * bet["fraction"] * exposure_scale

                if bet_amount > 0:
                    bettable_funds = bankroll.bettable_funds
                    if bet_amount > bettable_funds:
                        logger.warning(
                            f"Bet of {bet_amount:.2f} on {bet['label']} exceeds bettable funds "
                            f"({bettable_funds:.2f}); staking the capped amount instead."
                        )
                        bet_amount = bettable_funds

                if bet_amount > 0:
                    logger.debug(f"Betting {bet_amount:.2f} on {bet['label']} to win (Fraction: {bet['fraction']:.4f})")
                    bankroll_before = bankroll.total_funds
                    bankroll.bet(bet_amount)
                    stake = bet_amount
                    if bet["actual_outcome"]:
                        # Win: return bet amount plus winnings
                        bankroll.add_funds(bet_amount + bet_amount * bet["payoff"])
                        profit = stake * bet["payoff"]
                        logger.debug(f"Bet WON. Bankroll: {bankroll.total_funds:.2f}")
                    else:
                        # Loss: bet amount already deducted by bet()
                        profit = -stake
                        logger.debug(f"Bet LOST. Bankroll: {bankroll.total_funds:.2f}")
                else:
                    skipped_zero_stake = True
                    logger.debug(
                        f"Bet fraction {bet['fraction']:.4f} resulted in zero or invalid bet amount ({bet_amount:.2f}) for {bet['label']}."
                    )
            except Exception as e:
                stake, profit = 0.0, 0.0
                error = str(e)
                logger.error(f"Error processing bet for {bet['label']}: {e}. Bankroll: {bankroll.total_funds}")

            self.bet_history.append(
                {
                    "period": period_number,
                    "label": bet["label"],
                    "opponent": bet["opponent"],
                    "fraction": bet["fraction"],
                    "stake": stake,
                    "payoff": bet["payoff"],
                    "won": bet["actual_outcome"],
                    "profit": profit,
                    "bankroll_after": bankroll.total_funds,
                    "skipped_zero_stake": skipped_zero_stake,
                    "error": error,
                }
            )
            if stake > 0 and error is None:
                _record_result_on_strategy(strategy, bet["actual_outcome"], profit, bankroll_before)
        logger.info(f"End of period {period_number} betting. Bankroll: {bankroll.total_funds:.2f}")

    def run_summary(self) -> Dict[str, Any]:
        """Condenses ``bet_history`` into the run's headline counts.

        ``total_candidates`` covers every candidate the run considered;
        ``placed_bets`` moved money and settled; ``failed_bets`` counts candidates
        with an ``error`` -- an evaluation the strategy could not price, or a
        settlement that raised -- and ``failure_reasons`` maps each error message to
        its count; ``skipped_zero_stake`` counts stakes that scaled or clamped to
        zero; ``wins``/``losses`` cover the placed bets; ``net_profit`` is the sum of
        the ledger's profits. ``run_explicit`` clears ``bet_history`` at its start,
        so after a run this describes exactly that run; before any run it is all
        zeros.
        """
        return summarize_bet_history(self.bet_history)

    def run_explicit(
        self,
        data: Dict[int, List[GameRecord]],
        strategy: BaseStrategy,
        bankroll: BankRoll,
        period_to_start_betting: int = 3,
        price_bets_at_true_odds: bool = True,
    ) -> BankRoll:
        """Runs a backtest simulation, processing data period by period.

        Calls the strategy's `evaluate` method with `probability` and
        `current_bankroll`, then handles bankroll updates using the explicitly
        passed bankroll object.

        Data format requires `winner_odds` and `loser_odds` to be American odds.

        :param data: Historical game data keyed by period.
        :type data: Dict[int, List[GameRecord]]
        :param strategy: An initialized betting strategy instance.
        :type strategy: BaseStrategy
        :param bankroll: An initialized keeks.bankroll.BankRoll instance.
        :type bankroll: BankRoll
        :param period_to_start_betting: The period *after* which the strategy should start issuing
                                          real bets (periods before this are dry runs).
                                          Defaults to 3.
        :type period_to_start_betting: int
        :param price_bets_at_true_odds: Size each bet using its game-specific payoff.
                                       If false, use the strategy's configured payoff
                                       for sizing. Settlement always uses the game's
                                       actual odds. Defaults to true.
        :type price_bets_at_true_odds: bool
        :return: The BankRoll object, updated with results from the backtest.
        :rtype: BankRoll

        Strategies that expose keeks' ``record_result(won, return_pct)`` hook are
        notified of every bet the run actually settles -- always on the ``strategy``
        instance passed in, even when each bet is priced by a freshly constructed
        re-priced copy -- so stateful strategies such as
        ``DynamicBankrollManagement`` update their state mid-run. Strategies without
        the hook are unaffected, and candidates that move no money (a zero stake or
        a failed settlement) notify nothing.

        Every wager this run settles is also recorded on ``self.bet_history``, which is
        cleared at the start of each call so re-running the same ``Backtest`` never
        appends to a previous run's records. Each entry is a dict with:

        ``period``
            The period the bet settled in (one after the period it was priced in);
            for a failed evaluation, the period the candidate would have settled in.
        ``label`` / ``opponent``
            The competitor backed and the other side of the game.
        ``fraction``
            The stake fraction the strategy quoted, or ``None`` when it raised
            before quoting one.
        ``stake``
            The amount actually staked, after the period's exposure scaling and after
            the residual clamp against live ``bettable_funds``.
        ``payoff``
            The game's decimal odds minus one.
        ``won``
            Whether the backed competitor won.
        ``profit``
            ``stake * payoff`` on a win, ``-stake`` on a loss.
        ``bankroll_after``
            ``bankroll.total_funds`` once this bet had settled.
        ``skipped_zero_stake`` / ``error``
            Flags for the candidates that moved no money: a stake that scaled or
            clamped to zero, a settlement that raised, and an evaluation the strategy
            could not price. An evaluation failure is recorded the moment the strategy
            raises -- with ``fraction`` of ``None``, since no stake was ever quoted --
            so a strategy that fails on every bet produces a ledger of failed
            candidates and a non-zero ``failed_bets`` count in :meth:`run_summary`
            rather than an empty, plausible-looking run. All of them carry ``stake``
            and ``profit`` of ``0.0``, so every candidate the run considered is
            accounted for rather than silently omitted.

        :meth:`run_summary` condenses the ledger into counts -- placed, failed (with
        the reasons), skipped for a zero stake, wins, losses and net profit -- and the
        headline counts are logged when the run finishes.
        """
        logger.info("Starting explicit backtest run.")
        self.bet_history = []
        logger.debug(f"Using strategy: {type(strategy).__name__} with bankroll: {bankroll.total_funds}")
        logger.debug(f"Period to start betting: {period_to_start_betting}")

        data = prepare_data(data)
        logger.debug(f"Prepared data keys (periods): {list(data.keys())}")
        period_keys = sorted(data)

        bets_calculated_prev_period: List[Dict[str, Any]] = []  # Store bets for execution in the *next* period

        for period_index, week_no in enumerate(period_keys):
            games = data[week_no]
            logger.info(f"Processing period {week_no} with {len(games)} games.")

            current_period_bets_to_execute = bets_calculated_prev_period

            # --- Execute bets for the *current* period (calculated in the previous iteration) ---
            is_betting_period = week_no > period_to_start_betting
            if is_betting_period:
                self._execute_bets_for_current_period(strategy, bankroll, current_period_bets_to_execute, week_no)

            # --- Update Arena Ratings with *current* period results ---
            matchups = [_matchup_tuple(x) for x in games]
            if matchups:
                logger.info(f"Updating arena ratings with {len(matchups)} matchups from period {week_no}.")
                self._arena.tournament(matchups)
                logger.debug(f"Arena update complete for period {week_no}.")
            else:
                logger.info(f"No matchups to update ratings for period {week_no}.")

            # --- Evaluate potential bets for the *next* period ---
            next_period_key = period_keys[period_index + 1] if period_index + 1 < len(period_keys) else None
            next_period_games = data[next_period_key] if next_period_key is not None else []
            bets_calculated_this_period = self._evaluate_bets_for_next_period(
                strategy,
                bankroll,
                next_period_games,
                price_bets_at_true_odds,
                next_period_number=next_period_key,
            )

            if not is_betting_period:
                logger.info(
                    f"Period {week_no}: Dry run week. Calculated {len(bets_calculated_this_period)} potential bets for next period."
                )

            # Store calculated bets for the next iteration
            bets_calculated_prev_period = bets_calculated_this_period

        summary = self.run_summary()
        logger.info(
            "Explicit backtest run finished: %d bets placed, %d failed, %d skipped for a zero stake.",
            summary["placed_bets"],
            summary["failed_bets"],
            summary["skipped_zero_stake"],
        )
        return bankroll  # Return the updated bankroll object

    def run_and_project(self, data: Dict[int, List[GameRecord]]) -> List[ProjectionRecord]:
        """Runs a simulation focused on generating and logging future projections.

        This method iterates through historical periods, updating the arena ratings
        based on game outcomes. For each period, it then uses the updated ratings
        to calculate and log win probabilities for the games scheduled in the *next*
        period.

        No betting simulation is performed.

        The expected data schema is the same as for ``run_explicit``, although odds
        are not used in this method.

        :param data: Historical game data keyed by period.
        :type data: Dict[int, List[GameRecord]]
        :return: One record per projected game -- the projected period, the model's
            favored side, and its win probability (always >= 0.5) -- in schedule
            order. The same predictions are also logged, for interactive use.
        :rtype: List[ProjectionRecord]
        """
        logger.info("Starting projection run.")
        data = prepare_data(data)
        logger.debug(f"Prepared data keys (periods): {list(data.keys())}")
        period_keys = sorted(data)
        projections: List[ProjectionRecord] = []

        for period_index, week_no in enumerate(period_keys):
            games = data[week_no]
            logger.info(f"Processing period {week_no} with {len(games)} games.")
            # print('\nrunning with week %s' % (week_no,)) # Replaced with logging

            matchups = [_matchup_tuple(x) for x in games]
            # Only update ratings if there were games in the period
            if matchups:
                logger.info(f"Updating arena ratings with {len(matchups)} matchups from period {week_no}.")
                self._arena.tournament(matchups)
                logger.debug(f"Arena update complete for period {week_no}.")
            else:
                logger.info(f"No matchups to update ratings for period {week_no}.")

            next_period_key = period_keys[period_index + 1] if period_index + 1 < len(period_keys) else None
            next_period_games = data[next_period_key] if next_period_key is not None else []
            projected_period = next_period_key if next_period_key is not None else week_no + 1
            logger.info(f"Generating projections for period {projected_period} ({len(next_period_games)} games).")
            for game in next_period_games:
                winner, loser = game.get("winner"), game.get("loser")
                if winner is None or loser is None:
                    logger.warning(f"Skipping game due to missing labels: {game}")
                    continue
                logger.debug(f"Projecting game: {winner} vs {loser}")
                prob_win = calculate_probabilities(self._arena, game)
                if prob_win > 0.5:
                    logger.info(f"Predicted {winner} over {loser}: {prob_win:.4f}")
                    projections.append(
                        {
                            "period": projected_period,
                            "predicted_winner": winner,
                            "predicted_loser": loser,
                            "probability": prob_win,
                        }
                    )
                else:
                    # If prob_win <= 0.5, the model favors the listed 'loser'
                    logger.info(f"Predicted {loser} over {winner}: {1.0 - prob_win:.4f}")
                    projections.append(
                        {
                            "period": projected_period,
                            "predicted_winner": loser,
                            "predicted_loser": winner,
                            "probability": 1.0 - prob_win,
                        }
                    )

        logger.info("Projection run finished.")
        return projections
