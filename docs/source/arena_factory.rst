Arena factory
=============

``keeks_elote.arena_factory`` maps a rating system's name to its elote competitor
class, so building the arena that drives the backtests is one line:

.. code-block:: python

   from keeks_elote import create_arena

   arena = create_arena("glicko")

``LambdaArena`` is elote's general-purpose arena, but building one by hand means
importing it, picking the competitor class that implements the rating system you
want, and remembering elote's constructor keyword names. Every elote competitor
class that implements a single rating system is mapped here;
``BlendedCompetitor`` is deliberately absent -- it is a composite over other
competitors, not a rating system of its own, so it has no name a
``rating_system`` argument could mean.

Supported rating systems
------------------------

.. data:: keeks_elote.arena_factory.RATING_SYSTEMS

   Every supported ``rating_system`` name, mapped to the elote competitor class
   that implements it. The names are the factory's public vocabulary:

   ``bradley-terry``, ``colley``, ``dwz``, ``ecf``, ``elo``, ``glicko``,
   ``glicko2``, ``keener``, ``massey``, ``pythagorean``, ``trueskill``, ``whr``

   An unknown name raises a ``ValueError`` listing the supported ones.

The factory
-----------

.. function:: keeks_elote.arena_factory.create_arena(rating_system="glicko", base_kwargs=None, **arena_kwargs)

   Builds a configured elote ``LambdaArena`` for a named rating system.

   :param rating_system: One of the names in :data:`RATING_SYSTEMS`. Defaults
                         to ``"glicko"``.
   :param base_kwargs: Keyword arguments for the rating system's competitor
                       constructor -- ``{"initial_rating": 2100}`` for Glicko,
                       for example. Defaults to the competitor class's own
                       defaults.
   :param arena_kwargs: Further keyword arguments are forwarded to the
                        ``LambdaArena`` constructor itself, so callers can pass
                        ``func`` (the comparison function for bare ``(a, b)``
                        pairs) or ``initial_state``.
   :returns: A ``LambdaArena`` whose competitors are the named rating system,
             satisfying the :class:`~keeks_elote.rating_arena.RatingArena`
             protocol :class:`~keeks_elote.backtest.Backtest` drives.
   :raises ValueError: If ``rating_system`` is not a supported name. The
                       message lists the supported names.

The arena's default comparison function always answers "the first competitor
wins". That is the right default for the backtest flow -- every game's recorded
result is forwarded to the arena, so the comparison function is never consulted
-- but callers rating bare ``(a, b)`` pairs, where the arena really does have to
decide, should supply their own ``func``.
