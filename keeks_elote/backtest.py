import logging
from typing import Any, Dict, List

from elote.arenas.base import BaseArena
from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote.data_handling import prepare_data
from keeks_elote.model_evaluation import calculate_probabilities

logger = logging.getLogger(__name__)


# Helper to convert American odds to decimal odds
def american_to_decimal(american_odds: float) -> float:
    if american_odds >= 0:
        return (american_odds / 100.0) + 1.0
    else:
        return (100.0 / abs(american_odds)) + 1.0


class Backtest:
    """Runs backtests for betting strategies using an elote Arena for ratings.

    This class orchestrates the process of simulating historical periods (e.g., weeks),
    updating competitor ratings based on outcomes, generating betting opportunities
    for future periods, and evaluating a given betting strategy against those
    opportunities.

    Requires the strategy object to have an associated `bankroll` attribute of type
    `keeks.bankroll.BankRoll`.

    :param arena: An initialized elote Arena instance (e.g., GlickoArena).
    :type arena: BaseArena
    """

    def __init__(self, arena: BaseArena):
        """Initializes the Backtest environment.

        :param arena: An initialized elote Arena instance.
        :type arena: BaseArena
        """
        logger.info(f"Initializing Backtest with arena: {type(arena).__name__}")
        self._arena = arena

    def _evaluate_bets_for_next_period(
        self,
        strategy: BaseStrategy,
        next_period_games: List[Dict[str, Any]],
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
                if winner_odds_american is not None:
                    try:
                        decimal_odds_winner = american_to_decimal(winner_odds_american)
                        bet_fraction_winner = strategy.evaluate(probability=prob_winner_wins)
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
                if loser_odds_american is not None:
                    try:
                        decimal_odds_loser = american_to_decimal(loser_odds_american)
                        bet_fraction_loser = strategy.evaluate(probability=prob_loser_wins)
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
        """Executes a list of bets against the provided bankroll."""
        logger.info(f"Period {period_number}: Executing {len(bets_to_execute)} bets calculated previously.")
        for bet in bets_to_execute:
            try:
                available_to_bet = bankroll.total_funds * bankroll.percent_bettable
                bet_amount = available_to_bet * bet["fraction"]

                if bet_amount > 0 and bet_amount <= available_to_bet:
                    logger.debug(f"Betting {bet_amount:.2f} on {bet['label']} to win (Fraction: {bet['fraction']:.4f})")
                    if bet["actual_outcome"]:
                        bankroll.win_bet(bet_amount, bet["payoff"])
                        logger.debug(f"Bet WON. Bankroll: {bankroll.total_funds:.2f}")
                    else:
                        bankroll.lose_bet(bet_amount)
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
    ) -> BankRoll:
        """Runs a backtest simulation, processing data period by period.

        Calls the strategy's `evaluate` method (assuming it takes `probability`,
        `payoff`, `loss` and returns a bet fraction) and handles bankroll updates
        using the explicitly passed bankroll object.

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
        :return: The BankRoll object, updated with results from the backtest.
        :rtype: BankRoll
        """
        logger.info("Starting explicit backtest run.")
        logger.debug(f"Using strategy: {type(strategy).__name__} with bankroll: {bankroll.total_funds}")
        logger.debug(f"Period to start betting: {period_to_start_betting}")

        data = prepare_data(data)
        logger.debug(f"Prepared data keys (periods): {list(data.keys())}")

        bets_calculated_prev_period = []  # Store bets for execution in the *next* period

        for week_no, games in data.items():
            logger.info(f"Processing period {week_no} with {len(games)} games.")

            current_period_bets_to_execute = bets_calculated_prev_period

            # --- Evaluate potential bets for the *next* period (week_no + 1) ---
            next_period_games = data.get(week_no + 1, [])
            bets_calculated_this_period = self._evaluate_bets_for_next_period(strategy, next_period_games)

            # --- Execute bets for the *current* period (calculated in the previous iteration) ---
            is_betting_period = week_no > period_to_start_betting
            if not is_betting_period:
                logger.info(
                    f"Period {week_no}: Dry run week. Calculated {len(bets_calculated_this_period)} potential bets for next period."
                )
            else:
                self._execute_bets_for_current_period(bankroll, current_period_bets_to_execute, week_no)

            # --- Update Arena Ratings with *current* period results ---
            matchups = [(x.get("winner"), x.get("loser")) for x in games]
            if matchups:
                logger.info(f"Updating arena ratings with {len(matchups)} matchups from period {week_no}.")
                self._arena.tournament(matchups)
                logger.debug(f"Arena update complete for period {week_no}.")
            else:
                logger.info(f"No matchups to update ratings for period {week_no}.")

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

        for week_no, games in data.items():
            logger.info(f"Processing period {week_no} with {len(games)} games.")
            # print('\nrunning with week %s' % (week_no,)) # Replaced with logging

            matchups = [(x.get("winner"), x.get("loser")) for x in games]
            # Only update ratings if there were games in the period
            if matchups:
                logger.info(f"Updating arena ratings with {len(matchups)} matchups from period {week_no}.")
                self._arena.tournament(matchups)
                logger.debug(f"Arena update complete for period {week_no}.")
            else:
                logger.info(f"No matchups to update ratings for period {week_no}.")

            next_period_games = data.get(week_no + 1, [])
            logger.info(f"Generating projections for period {week_no + 1} ({len(next_period_games)} games).")
            for game in next_period_games:
                logger.debug(f"Projecting game: {game.get('winner')} vs {game.get('loser')}")
                prob_win = calculate_probabilities(self._arena, game)
                winner, loser = game.get("winner"), game.get("loser")
                if prob_win > 0.5:
                    logger.info(f"Predicted {winner} over {loser}: {prob_win:.4f}")
                    # print('Predicted %s over %s: %s' % (game.get('winner'), game.get('loser'), prob_win, )) # Replaced
                else:
                    # If prob_win <= 0.5, the model favors the listed 'loser'
                    logger.info(f"Predicted {loser} over {winner}: {1.0 - prob_win:.4f}")
                    # print('Predicted %s over %s: %s' % (game.get('loser'), game.get('winner'), prob_win, )) # Incorrect output previously

        logger.info("Projection run finished.")
