"""The :func:`create_arena` factory: named one-line construction of an elote arena.

``LambdaArena`` is elote's general-purpose arena, but building one by hand means
importing it, picking the competitor class that implements the rating system you
want, and remembering elote's constructor keyword names. This module maps a
rating system's name to its elote competitor class so callers can write
``create_arena("glicko")``.

Every elote competitor class that implements a single rating system is mapped
here. ``BlendedCompetitor`` is deliberately absent: it is not a rating system of
its own but a composite over other competitors, so it has no name that a
``rating_system`` argument could mean.
"""

import logging
from typing import Any, Dict, Optional, Type

from elote import (
    BradleyTerryCompetitor,
    ColleyMatrixCompetitor,
    DWZCompetitor,
    ECFCompetitor,
    EloCompetitor,
    Glicko2Competitor,
    GlickoCompetitor,
    KeenerCompetitor,
    LambdaArena,
    MasseyCompetitor,
    PythagoreanCompetitor,
    TrueSkillCompetitor,
    WholeHistoryRatingCompetitor,
)
from elote.competitors.base import BaseCompetitor

logger = logging.getLogger(__name__)


def _first_competitor_wins(a: Any, b: Any) -> bool:
    """Default comparison function, mirroring ``examples/cfb.py``.

    keeks-elote's backtest always forwards a game's recorded result to the arena
    (the outcome is pinned to 1.0 from the winner's perspective), so the
    comparison function is never asked to decide a result the data already
    knows. This trivial default exists for that flow; callers rating bare
    ``(a, b)`` pairs -- where the arena really does have to decide -- should
    pass their own ``func`` through :func:`create_arena`.
    """
    return True


#: Every supported ``rating_system`` name, mapped to the elote competitor class
#: that implements it. The names are the factory's public vocabulary; an
#: unknown name raises a :class:`ValueError` listing them.
RATING_SYSTEMS: Dict[str, Type[BaseCompetitor]] = {
    "bradley-terry": BradleyTerryCompetitor,
    "colley": ColleyMatrixCompetitor,
    "dwl": DWZCompetitor,
    "ecf": ECFCompetitor,
    "elo": EloCompetitor,
    "glicko": GlickoCompetitor,
    "glicko2": Glicko2Competitor,
    "keener": KeenerCompetitor,
    "massey": MasseyCompetitor,
    "pythagorean": PythagoreanCompetitor,
    "trueskill": TrueSkillCompetitor,
    "whr": WholeHistoryRatingCompetitor,
}


def create_arena(
    rating_system: str = "glicko",
    base_kwargs: Optional[Dict[str, Any]] = None,
    **arena_kwargs: Any,
) -> LambdaArena:
    """Builds a configured elote ``LambdaArena`` for a named rating system.

    :param rating_system: One of the names in :data:`RATING_SYSTEMS`
        (``bradley-terry``, ``colley``, ``dwl``, ``ecf``, ``elo``, ``glicko``,
        ``glicko2``, ``keener``, ``massey``, ``pythagorean``, ``trueskill``,
        ``whr``). Defaults to ``"glicko"``.
    :type rating_system: str
    :param base_kwargs: Keyword arguments for the rating system's competitor
        constructor -- ``{"initial_rating": 2100}`` for Glicko, for example.
        Defaults to the competitor class's own defaults.
    :type base_kwargs: Optional[Dict[str, Any]]
    :param arena_kwargs: Further keyword arguments are forwarded to the
        ``LambdaArena`` constructor itself, so callers can pass ``func`` (the
        comparison function for bare ``(a, b)`` pairs) or ``initial_state``.
    :return: A ``LambdaArena`` whose competitors are the named rating system,
        satisfying the :class:`~keeks_elote.rating_arena.RatingArena` protocol
        :class:`~keeks_elote.backtest.Backtest` drives.
    :rtype: LambdaArena
    :raises ValueError: If ``rating_system`` is not a supported name. The
        message lists the supported names.

    The arena's default comparison function always answers "the first
    competitor wins". That is the right default for the backtest flow -- every
    game's recorded result is forwarded, so the comparison function is never
    consulted -- but callers rating bare ``(a, b)`` pairs should supply their
    own ``func``.
    """
    competitor_class = RATING_SYSTEMS.get(rating_system)
    if competitor_class is None:
        raise ValueError(
            f"Unknown rating_system {rating_system!r}; supported systems are: "
            + ", ".join(sorted(RATING_SYSTEMS))
            + "."
        )

    logger.debug("Creating LambdaArena with rating system %r (%s).", rating_system, competitor_class.__name__)
    # The default comparison function is injected only when the caller did not
    # supply one -- passing it positionally would collide with a caller's own
    # ``func=`` on LambdaArena's first parameter.
    if "func" not in arena_kwargs:
        arena_kwargs["func"] = _first_competitor_wins
    return LambdaArena(
        base_competitor=competitor_class,
        base_competitor_kwargs=base_kwargs,
        **arena_kwargs,
    )
