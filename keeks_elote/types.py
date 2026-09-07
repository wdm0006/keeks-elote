"""Typed schemas for keeks-elote's public surface.

These types document the contracts that actually flow through the glue layer: the
game records callers pass in, the matchup tuples forwarded to an arena's
``tournament``, and the projection records :meth:`Backtest.run_and_project` returns.
They are annotations only -- game records arrive as plain dicts at runtime, so the
parser stays lenient with malformed values (warned about and handled, never trusted).
"""

from typing import Any, Tuple, TypedDict, Union


class _GameRecordRequired(TypedDict):
    """The keys every game record must carry; ``prepare_data`` drops records without them."""

    winner: str
    loser: str


class GameRecord(_GameRecordRequired, total=False):
    """One historical game, as consumed by :class:`~keeks_elote.backtest.Backtest`.

    ``winner``/``loser`` are the recorded labels -- the first names the side that
    won -- and are the only required keys. The optional keys are consumed when
    present: ``winner_odds``/``loser_odds`` are American odds and drive bet pricing,
    while ``winner_score``/``loser_score`` feed the margin-aware rating systems
    (Massey, Keener, Pythagorean) through the matchup tuple's score pair.

    The runtime parser is deliberately lenient with those optional values:
    unparseable or self-contradicting scores degrade to result-only rating with a
    warning instead of failing the run. This schema is therefore the contract
    well-formed input should meet, not a guarantee the parser enforces.
    """

    winner_odds: float
    loser_odds: float
    winner_score: float
    loser_score: float


class ProjectionRecord(TypedDict):
    """One projected game, as returned by :meth:`Backtest.run_and_project`.

    ``predicted_winner`` is the side the model favors and ``probability`` is the
    model's win probability for that side, so it is always ``>= 0.5``. The record
    mirrors the prediction log lines the run also emits, in a structure a caller
    can aggregate.
    """

    period: int
    predicted_winner: str
    predicted_loser: str
    probability: float


# The matchup payloads keeks-elote forwards to an arena's ``tournament``. elote
# splats each element into ``matchup(a, b, attributes, match_time, outcome, scores)``,
# so a bare pair defers to the arena's comparison function, while the 5- and 6-tuple
# forms pin the recorded result -- outcome 1.0, from the first competitor's
# perspective -- and optionally carry the score pair that margin-aware systems read
# positionally as (first competitor's score, second competitor's score).
MatchupTuple = Union[
    Tuple[Any, Any],
    Tuple[Any, Any, None, None, float],
    Tuple[Any, Any, None, None, float, Tuple[float, float]],
]
