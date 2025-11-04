"""Pytest configuration for keeks-elote tests.

This module sets up fixtures and workarounds for testing.
"""

import sys
import types


# Workaround for elote 1.1.0 dataset import issue
# elote always tries to import chess even when datasets feature is not used
def _mock_chess_modules():
    """Mock chess and pyzstd modules to allow elote to import without these dependencies."""
    if 'chess' not in sys.modules:
        chess = types.ModuleType('chess')
        chess.pgn = types.ModuleType('chess.pgn')
        chess.pgn.Game = type('Game', (), {})
        chess.Board = type('Board', (), {})
        sys.modules['chess'] = chess
        sys.modules['chess.pgn'] = chess.pgn

    if 'pyzstd' not in sys.modules:
        pyzstd = types.ModuleType('pyzstd')
        sys.modules['pyzstd'] = pyzstd


# Mock chess modules before any imports
_mock_chess_modules()
