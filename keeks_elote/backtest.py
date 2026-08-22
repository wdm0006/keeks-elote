import copy
import logging
import math
import numbers
from typing import Any, Dict, List, Optional, Tuple

from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote.data_handling import prepare_data
from keeks_elote.model_evaluation import calculate_probabilities
from keeks_elote.rating_arena import RatingArena

logger = logging.getLogger(__name__)


# Helper to convert American odds to decimal odds
def _matchup_tuple(game: Dict[str, Any]) -> Tuple[Any, ...]:
    """Build the arena matchup tuple for a settled game.

    Rating systems that model margin of victory (Massey, Keener, Pythagorean) need the
    scores, not just who won. elote's ``tournament`` unpacks each tuple into ``matchup``,
    whose signature is ``(a, b, attributes, match_time, outcome, scores)``, so a game
    carrying ``winner_score`` and ``loser_score`` is forwarded with them and every other
    game keeps the plain two-element form the win/loss systems expect.
    """
    winner, loser = game.get("winner"), game.get("loser")
    winner_score, loser_score = game.get("winner_score"), game.get("loser_score")
    if winner_score is None or loser_score is None:
        return (winner, loser)
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
        return (winner, loser)
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
        return (winner, loser)

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


def _strategy_for_bet(strategy: BaseStrategy, payoff: float, price_bets_at_true_odds: bool) -> BaseStrategy:
    if not price_bets_at_true_odds:
        return strategy

    bet_strategy = copy.copy(strategy)
    bet_strategy.payoff = payoff
    bet_strategy.loss = 1.0
    return bet_strategy


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

    def _evaluate_bets_for_next_period(
        self,
        strategy: BaseStrategy,
        bankroll: BankRoll,
        next_period_games: List[Dict[str, Any]],
        price_bets_at_true_odds: bool,
    ) -> List[Dict[str, Any]]:
        """Evaluates potential bets for a given list of games."""
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
            else:
                logger.debug(
                    f"Skipping game {game.get('winner')} vs {game.get('loser')} for opportunities (missing odds or labels)."
                )
        return bets_calculated

    def _execute_bets_for_current_period(
        self,
        bankroll: BankRoll,
        bets_to_execute: List[Dict[str, Any]],
        period_number: int,
    ) -> None:
        """Executes a list of bets against the provided bankroll.

        Every bet is sized as ``opening_funds * fraction``, the same base the
        strategy was quoted against, so wagers inside a period do not compound
        off each other.

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
                    bankroll.bet(bet_amount)
                    if bet["actual_outcome"]:
                        # Win: return bet amount plus winnings
                        bankroll.add_funds(bet_amount + bet_amount * bet["payoff"])
                        logger.debug(f"Bet WON. Bankroll: {bankroll.total_funds:.2f}")
                    else:
                        # Loss: bet amount already deducted by bet()
                        logger.debug(f"Bet LOST. Bankroll: {bankroll.total_funds:.2f}")
                else:
                    logger.debug(
                        f"Bet fraction {bet['fraction']:.4f} resulted in zero or invalid bet amount ({bet_amount:.2f}) for {bet['label']}."
                    )
            except Exception as e:
                logger.error(f"Error processing bet for {bet['label']}: {e}. Bankroll: {bankroll.total_funds}")
        logger.info(f"End of period {period_number} betting. Bankroll: {bankroll.total_funds:.2f}")

    def run_explicit(
        self,
        data: Dict[int, List[Dict[str, Any]]],
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
        :type data: Dict[int, List[Dict[str, Any]]]
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
        """
        logger.info("Starting explicit backtest run.")
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
                self._execute_bets_for_current_period(bankroll, current_period_bets_to_execute, week_no)

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
            )

            if not is_betting_period:
                logger.info(
                    f"Period {week_no}: Dry run week. Calculated {len(bets_calculated_this_period)} potential bets for next period."
                )

            # Store calculated bets for the next iteration
            bets_calculated_prev_period = bets_calculated_this_period

        logger.info("Explicit backtest run finished.")
        return bankroll  # Return the updated bankroll object

    def run_and_project(self, data: Dict[int, List[Dict[str, Any]]]):
        """Runs a simulation focused on generating and logging future projections.

        This method iterates through historical periods, updating the arena ratings
        based on game outcomes. For each period, it then uses the updated ratings
        to calculate and log win probabilities for the games scheduled in the *next*
        period.

        No betting simulation is performed.

        The expected data schema is the same as for ``run_explicit``, although odds
        are not used in this method.

        :param data: Historical game data keyed by period.
        :type data: Dict[int, List[Dict[str, Any]]]
        """
        logger.info("Starting projection run.")
        data = prepare_data(data)
        logger.debug(f"Prepared data keys (periods): {list(data.keys())}")
        period_keys = sorted(data)

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
                    # print('Predicted %s over %s: %s' % (game.get('winner'), game.get('loser'), prob_win, )) # Replaced
                else:
                    # If prob_win <= 0.5, the model favors the listed 'loser'
                    logger.info(f"Predicted {loser} over {winner}: {1.0 - prob_win:.4f}")
                    # print('Predicted %s over %s: %s' % (game.get('loser'), game.get('winner'), prob_win, )) # Incorrect output previously

        logger.info("Projection run finished.")
