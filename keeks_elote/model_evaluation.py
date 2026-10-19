import logging
import math
from collections import defaultdict
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from keeks_elote.arena_factory import RATING_SYSTEMS, create_arena
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
    _check_epsilon(epsilon)
    matched = _match_projections(projections, data)
    return _aggregate(matched, epsilon)


def score_projections_by_period(
    projections: Sequence[ProjectionRecord],
    data: Dict[int, List[GameRecord]],
    epsilon: float = 1e-15,
) -> Dict[Any, Dict[str, Any]]:
    """Scores projections like :func:`score_projections`, one entry per projected period.

    Every period that appears in ``projections`` gets ``{n, skipped, accuracy,
    log_loss, brier}``, in ascending period order. A period whose projections all
    lack a recorded game has ``n == 0`` and ``None`` rates.

    :param projections: Records returned by ``run_and_project``.
    :param data: The period-keyed games the projections were made from.
    :param epsilon: Clamp for the log-loss probabilities, in ``(0, 0.5)``.
    """
    _check_epsilon(epsilon)
    grouped: Dict[Any, List[Tuple[ProjectionRecord, Optional[bool]]]] = defaultdict(list)
    for projection, hit in _match_projections(projections, data):
        grouped[projection["period"]].append((projection, hit))
    result: Dict[Any, Dict[str, Any]] = {}
    for period in sorted(grouped):
        scored = _aggregate(grouped[period], epsilon)
        result[period] = {key: scored[key] for key in ("n", "skipped", "accuracy", "log_loss", "brier")}
    return result


def calibration_table(
    projections: Sequence[ProjectionRecord],
    data: Dict[int, List[GameRecord]],
    bins: int = 10,
) -> List[Dict[str, Any]]:
    """Bins matched projections by favourite probability and compares it with the hit rate.

    ``bins`` equal-width bins span ``[0, 1]`` (lower edge inclusive, the last bin also
    includes 1.0). Each row is ``{lo, hi, n, mean_predicted, observed_rate}``; empty
    bins are kept with ``n == 0`` and ``None`` rates. Unmatched projections are not
    binned (see ``skipped`` in :func:`score_projections`).

    :param projections: Records returned by ``run_and_project``.
    :param data: The period-keyed games the projections were made from.
    :param bins: Number of bins, a positive integer.
    """
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 1:
        raise ValueError(f"bins must be a positive integer, got {bins!r}")
    counts = [0] * bins
    probability_sums = [0.0] * bins
    hits = [0] * bins
    for projection, hit in _match_projections(projections, data):
        if hit is None:
            continue
        probability = float(projection["probability"])
        index = min(max(int(probability * bins), 0), bins - 1)
        counts[index] += 1
        probability_sums[index] += probability
        hits[index] += hit
    return [
        {
            "lo": i / bins,
            "hi": (i + 1) / bins,
            "n": counts[i],
            "mean_predicted": probability_sums[i] / counts[i] if counts[i] else None,
            "observed_rate": hits[i] / counts[i] if counts[i] else None,
        }
        for i in range(bins)
    ]


def _check_epsilon(epsilon: float) -> None:
    if not 0.0 < epsilon < 0.5:
        raise ValueError(f"epsilon must be in (0, 0.5), got {epsilon!r}")


def _match_projections(
    projections: Sequence[ProjectionRecord],
    data: Dict[int, List[GameRecord]],
) -> List[Tuple[ProjectionRecord, Optional[bool]]]:
    """Joins each projection to its recorded game: ``True``/``False`` for hit/miss, ``None`` if unmatched."""
    recorded: Dict[Tuple[Any, FrozenSet[Any]], List[Any]] = defaultdict(list)
    for period, games in data.items():
        for game in games:
            winner, loser = game.get("winner"), game.get("loser")
            if winner is None or loser is None:
                continue
            recorded[(period, frozenset((winner, loser)))].append(winner)

    matched: List[Tuple[ProjectionRecord, Optional[bool]]] = []
    for projection in projections:
        key = (projection["period"], frozenset((projection["predicted_winner"], projection["predicted_loser"])))
        winners = recorded.get(key)
        if not winners:
            matched.append((projection, None))
            continue
        matched.append((projection, winners.pop(0) == projection["predicted_winner"]))
    return matched


def _aggregate(matched: Sequence[Tuple[ProjectionRecord, Optional[bool]]], epsilon: float) -> Dict[str, Any]:
    correct = 0
    skipped = 0
    log_loss_sum = 0.0
    brier_sum = 0.0
    probabilities: List[float] = []
    for projection, hit in matched:
        if hit is None:
            skipped += 1
            continue
        probability = float(projection["probability"])
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


def compare_rating_systems(
    data: Dict[int, List[GameRecord]],
    systems: Optional[Sequence[str]] = None,
    arena_kwargs: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Scores each named rating system's ``run_and_project`` forecasts on one dataset.

    For every name in ``systems`` (default: all of ``RATING_SYSTEMS``) a FRESH arena is
    built with :func:`create_arena`, driven through ``Backtest.run_and_project(data)`` and
    scored with :func:`score_projections`, so no system sees another's state.

    Evaluation protocol: the data is frozen and every system projects every period after
    the first from the ratings built so far. There is no warm-up cutoff on scoring, so
    early periods are predicted from almost no history. Numbers from this protocol are
    not comparable with walk-forward or train/test-split figures.

    A system that raises is recorded as ``{"system", "error"}`` instead of aborting the
    sweep. Unknown system names (in ``systems`` or ``arena_kwargs``) raise ``ValueError``
    before anything runs.

    :param data: Period-keyed games, as for ``Backtest.run_and_project``.
    :param systems: Rating-system names to compare; defaults to all of them.
    :param arena_kwargs: Optional ``{system: kwargs}`` forwarded to ``create_arena`` for
        that system (e.g. ``{"glicko": {"base_kwargs": {"initial_rating": 2100}}}``).
    :return: One row per system: ``{system, n, skipped, accuracy, log_loss, brier,
        min_probability, max_probability}``, sorted by ascending log loss with rows whose
        log loss is ``None`` after the scored ones and ``error`` rows last.
    """
    from keeks_elote.backtest import Backtest

    names = list(RATING_SYSTEMS) if systems is None else list(systems)
    overrides = arena_kwargs or {}
    unknown = sorted({n for n in [*names, *overrides] if n not in RATING_SYSTEMS}, key=str)
    if unknown:
        raise ValueError(
            f"Unknown rating system(s) {unknown!r}; supported systems are: " + ", ".join(sorted(RATING_SYSTEMS)) + "."
        )

    rows: List[Dict[str, Any]] = []
    for name in names:
        try:
            arena = create_arena(name, **dict(overrides.get(name, {})))
            projections = Backtest(arena).run_and_project(data)
            rows.append({"system": name, **score_projections(projections, data)})
        except Exception as exc:
            logger.warning("Rating system %r failed: %s", name, exc)
            rows.append({"system": name, "error": f"{type(exc).__name__}: {exc}"})

    def order(row: Dict[str, Any]) -> Tuple[int, float]:
        if "error" in row:
            return (2, 0.0)
        if row["log_loss"] is None:
            return (1, 0.0)
        return (0, row["log_loss"])

    return sorted(rows, key=order)
