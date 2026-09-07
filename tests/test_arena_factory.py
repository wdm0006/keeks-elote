"""Tests for the :func:`keeks_elote.create_arena` factory."""

import pytest
from elote import GlickoCompetitor, LambdaArena

from keeks_elote import create_arena
from keeks_elote.arena_factory import RATING_SYSTEMS
from keeks_elote.rating_arena import RatingArena

# The matchup shape the backtest forwards for a game with a recorded result and
# no usable scores: outcome pinned to 1.0 from the first competitor's perspective.
RECORDED_WIN = ("Alabama", "Auburn", None, None, 1.0)


@pytest.mark.parametrize("rating_system", sorted(RATING_SYSTEMS))
def test_create_arena_round_trip_per_supported_name(rating_system):
    """Every supported name builds an arena of the matching rating system that rates a settled game."""
    arena = create_arena(rating_system)

    assert isinstance(arena, LambdaArena)
    assert isinstance(arena, RatingArena)  # the protocol Backtest drives
    assert arena.base_competitor is RATING_SYSTEMS[rating_system]

    arena.tournament([RECORDED_WIN])
    probability = arena.expected_score("Alabama", "Auburn")
    assert 0.0 <= probability <= 1.0


def test_create_arena_defaults_to_glicko():
    arena = create_arena()

    assert arena.base_competitor is GlickoCompetitor


def test_base_kwargs_reach_the_competitor_constructor():
    """``base_kwargs`` configures the rating system's competitor class.

    A draw between two equally rated players leaves elote's Elo rating exactly
    unchanged, so the seeded ``initial_rating`` is observable after a game --
    deterministically, without depending on Elo's update math.
    """
    arena = create_arena("elo", base_kwargs={"initial_rating": 700}, func=lambda a, b: None)

    arena.tournament([("a", "b")])

    assert arena.competitors["a"].rating == 700
    assert arena.competitors["b"].rating == 700


def test_default_func_awards_the_first_competitor():
    """The built-in comparison function decides bare pairs for the first competitor.

    Backtests never hit this path -- recorded results are forwarded -- but it is
    the documented default, so it is pinned here.
    """
    arena = create_arena("elo")

    arena.tournament([("a", "b")])

    assert arena.competitors["a"].rating > arena.competitors["b"].rating


def test_arena_kwargs_are_forwarded():
    """Keyword arguments other than ``base_kwargs`` go to the LambdaArena constructor."""

    def comparison(a, b):
        return True

    arena = create_arena("glicko", func=comparison)

    assert arena.func is comparison


def test_unknown_rating_system_raises_a_clear_error():
    """An unknown name raises, naming the bad value and every supported name."""
    with pytest.raises(ValueError) as excinfo:
        create_arena("not-a-system")

    message = str(excinfo.value)
    assert "not-a-system" in message
    for supported in sorted(RATING_SYSTEMS):
        assert supported in message
