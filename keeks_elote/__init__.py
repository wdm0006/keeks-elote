"""Keeks Elote: Backtesting betting strategies with Elo-based ratings."""

import logging

from keeks_elote.backtest import Backtest

# Set up logger for the keeks_elote library
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.NullHandler())  # Default handler, does nothing unless configured

__all__ = ["Backtest"]
