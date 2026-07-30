from elote.arenas.lambda_arena import LambdaArena
from elote.competitors.glicko import GlickoCompetitor

from keeks_elote.rating_arena import RatingArena


def test_lambda_arena_satisfies_rating_arena_protocol():
    arena = LambdaArena(lambda _a, _b: True, base_competitor=GlickoCompetitor)

    assert isinstance(arena, RatingArena)
