"""Pin the package root's public surface: the documented re-exports and ``__all__``.

The re-export set is the documented public API -- the classes the README's
quickstart uses plus the working helpers the docs name -- so a rename that
documentation does not follow fails here, and an accidental addition to or
removal from the surface fails loudly too. This follows the pattern of keeks
#92, where tests assert the exact public surface.
"""

import keeks_elote
from keeks_elote import arena_factory, backtest, data_handling, model_evaluation, rating_arena, types

PINNED_SURFACE = [
    "Backtest",
    "GameRecord",
    "MatchupTuple",
    "ProjectionRecord",
    "RatingArena",
    "american_to_decimal",
    "calculate_probabilities",
    "create_arena",
    "edge",
    "load_csv",
    "load_dataframe",
    "pnl",
    "prepare_data",
    "roi",
    "summarize_bet_history",
    "to_decimal",
]


def test_all_is_the_pinned_surface():
    """__all__ is exactly the documented surface, in order -- no drift, no stowaways."""
    assert keeks_elote.__all__ == PINNED_SURFACE


def test_all_names_resolve():
    for name in keeks_elote.__all__:
        assert getattr(keeks_elote, name) is not None, name


def test_reexports_are_the_source_objects():
    """Each root export is the same object the defining module binds, not a copy."""
    assert keeks_elote.Backtest is backtest.Backtest
    assert keeks_elote.american_to_decimal is backtest.american_to_decimal
    assert keeks_elote.summarize_bet_history is backtest.summarize_bet_history
    assert keeks_elote.edge is backtest.edge
    assert keeks_elote.pnl is backtest.pnl
    assert keeks_elote.roi is backtest.roi
    assert keeks_elote.to_decimal is backtest.to_decimal
    assert keeks_elote.prepare_data is data_handling.prepare_data
    assert keeks_elote.load_csv is data_handling.load_csv
    assert keeks_elote.load_dataframe is data_handling.load_dataframe
    assert keeks_elote.calculate_probabilities is model_evaluation.calculate_probabilities
    assert keeks_elote.create_arena is arena_factory.create_arena
    assert keeks_elote.RatingArena is rating_arena.RatingArena
    assert keeks_elote.GameRecord is types.GameRecord
    assert keeks_elote.MatchupTuple is types.MatchupTuple
    assert keeks_elote.ProjectionRecord is types.ProjectionRecord
