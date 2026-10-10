import logging
import math
from collections import defaultdict
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord, ProjectionRecord

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


def score_projections(
    projections: Sequence[ProjectionRecord],
    data: Dict[int, List[GameRecord]],
    epsilon: float = 1e-15,
) -> Dict[str, Any]:
    """Scores :meth:`Backtest.run_and_project` forecasts against the recorded results in ``data``.

    Each projection is joined to a game of the same period and the same pair of
    competitors; the projection is correct when its ``predicted_winner`` is that
    game's recorded ``winner``. Repeated pairings in one period are matched in
    order. A projection with no matching recorded game is counted in ``skipped``
    rather than dropped silently.

    ``log_loss`` clamps each probability into ``[epsilon, 1 - epsilon]``;
    ``min_probability``/``max_probability`` are the raw, unclamped extremes, so a
    reader can see whether the clamp bound. With nothing scored, ``accuracy``,
    ``log_loss``, ``brier`` and the extremes are ``None``.

    :param projections: Records returned by ``run_and_project``.
    :param data: The period-keyed games the projections were made from.
    :param epsilon: Clamp for the log-loss probabilities, in ``(0, 0.5)``.
    :return: ``{n, skipped, accuracy, log_loss, brier, min_probability, max_probability}``.
    """
    if not 0.0 < epsilon < 0.5:
        raise ValueError(f"epsilon must be in (0, 0.5), got {epsilon!r}")

    recorded: Dict[Tuple[Any, FrozenSet[Any]], List[Any]] = defaultdict(list)
    for period, games in data.items():
        for game in games:
            winner, loser = game.get("winner"), game.get("loser")
            if winner is None or loser is None:
                continue
            recorded[(period, frozenset((winner, loser)))].append(winner)

    correct = 0
    skipped = 0
    log_loss_sum = 0.0
    brier_sum = 0.0
    probabilities: List[float] = []
    for projection in projections:
        key = (projection["period"], frozenset((projection["predicted_winner"], projection["predicted_loser"])))
        winners = recorded.get(key)
        if not winners:
            skipped += 1
            continue
        actual_winner = winners.pop(0)
        probability = float(projection["probability"])
        hit = actual_winner == projection["predicted_winner"]
        clamped = min(max(probability, epsilon), 1.0 - epsilon)
        correct += hit
        log_loss_sum -= math.log(clamped if hit else 1.0 - clamped)
        brier_sum += (probability - (1.0 if hit else 0.0)) ** 2
        probabilities.append(probability)

    n = len(probabilities)
    scored: Optional[int] = n or None
    return {
        "n": n,
        "skipped": skipped,
        "accuracy": correct / scored if scored else None,
        "log_loss": log_loss_sum / scored if scored else None,
        "brier": brier_sum / scored if scored else None,
        "min_probability": min(probabilities) if scored else None,
        "max_probability": max(probabilities) if scored else None,
    }
