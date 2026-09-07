"""Keeks Elote: Backtesting betting strategies with Elo-based ratings."""

import logging

from keeks_elote.backtest import Backtest
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord, MatchupTuple, ProjectionRecord

# Set up logger for the keeks_elote library
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())  # Default handler, does nothing unless configured

__all__ = ["Backtest", "GameRecord", "MatchupTuple", "ProjectionRecord", "RatingArena"]
