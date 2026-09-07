"""Keeks Elote: Backtesting betting strategies with Elo-based ratings."""

import logging

from keeks_elote.arena_factory import create_arena
from keeks_elote.backtest import (
    Backtest,
    american_to_decimal,
    edge,
    pnl,
    roi,
    summarize_bet_history,
    to_decimal,
)
from keeks_elote.data_handling import load_csv, load_dataframe, prepare_data
from keeks_elote.model_evaluation import calculate_probabilities
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord, MatchupTuple, ProjectionRecord

# Set up logger for the keeks_elote library
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())  # Default handler, does nothing unless configured

__all__ = [
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
