"""The structural type for the elote arenas keeks-elote drives."""

from typing import Any, List, Protocol, runtime_checkable

from keeks_elote.types import MatchupTuple


@runtime_checkable
class RatingArena(Protocol):
    """What an arena must expose for :class:`~keeks_elote.backtest.Backtest`.

    This types elote's real arena contract, not a pair-only sketch. ``tournament``
    receives the matchup tuples the backtest builds and splats each one into elote's
    ``matchup(a, b, attributes, match_time, outcome, scores)``. keeks-elote forwards
    either a bare ``(a, b)`` pair -- a game with no recorded result, which the
    arena's comparison function then decides -- or a 5- or 6-tuple that pins the
    recorded result, optionally with the score pair that margin-aware rating systems
    (Massey, Keener, Pythagorean) read positionally. See
    :data:`keeks_elote.types.MatchupTuple` for the exact shapes; implementations
    that accept elote's variadic ``List[Tuple[Any, ...]]`` satisfy this protocol.
    """

    def tournament(self, matchups: List[MatchupTuple]) -> Any: ...

    def expected_score(self, competitor: Any, opponent: Any) -> float: ...
