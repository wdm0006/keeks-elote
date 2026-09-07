import logging

from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord

logger = logging.getLogger(__name__)


def calculate_probabilities(arena: RatingArena, game: GameRecord) -> float:
    """Calculates the win probability for the 'winner' in a given game using the arena.

    This function retrieves the expected score (win probability) of the competitor
    listed as 'winner' against the competitor listed as 'loser' based on their
    current ratings within the provided elote Arena instance.

    :param arena: The elote Arena instance containing competitor ratings.
    :type arena: RatingArena
    :param game: The game to project, must contain 'winner' and 'loser' keys.
    :type game: GameRecord
    :return: The calculated win probability for the competitor listed as 'winner'.
    :rtype: float
    """
    winner = game.get("winner")
    loser = game.get("loser")
    logger.debug(f"Calculating expected score for {winner} vs {loser}.")
    # Example function to calculate probabilities
    prob_win = arena.expected_score(winner, loser)
    logger.debug(f"Expected score (P({winner})) = {prob_win:.4f}")
    return prob_win
