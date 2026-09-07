"""Backtesting a real EPL season: loaders, ratings, Kelly, edges, and metrics.

This example runs the whole keeks-elote flow over a real dataset -- the 2023-24
English Premier League season -- using only what the package root exports:

* ``load_csv`` turns ``data/epl_2023_24.csv`` into the period-keyed dict
  ``prepare_data`` consumes. The file holds the real 2023-24 EPL results with
  Bet365 closing prices (source: football-data.co.uk's 2023-24 ``E0.csv``);
  each ``period`` is one calendar week of the season, and the extra ``date``
  column rides along on every record. The season's 82 draws are excluded --
  the binary game schema has no third outcome -- leaving 298 decisive matches.
* ``create_arena("elo")`` builds the rating arena in one line.
* Every game carries decimal odds, so ``Backtest`` prices each candidate wager
  through the decimal-odds path and the Kelly criterion sizes it.
* After the run, ``edge`` re-prices the model's probabilities against the
  closing lines of the final matchweek (in-sample -- the ratings have already
  seen those results), and ``pnl``/``roi`` net the settled ledger.

Run from this directory:

    python epl.py
"""

import logging

from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

from keeks_elote import Backtest, calculate_probabilities, create_arena, edge, load_csv, pnl, roi

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATA_PATH = "./data/epl_2023_24.csv"


def main():
    logger.info("Loading matches with load_csv...")
    periods = load_csv(DATA_PATH)
    total_games = sum(len(games) for games in periods.values())
    logger.info("Loaded %d decisive matches across %d matchweeks.", total_games, len(periods))

    logger.info("Setting up the arena (create_arena), bankroll, and Kelly strategy...")
    arena = create_arena("elo")
    bank = BankRoll(initial_funds=1000, percent_bettable=0.5, max_draw_down=1.0)
    strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)

    logger.info("Running the season backtest (betting starts after matchweek 6)...")
    backtest = Backtest(arena)
    backtest.run_explicit(periods, strategy, bank, period_to_start_betting=6)

    summary = backtest.run_summary()
    logger.info(
        "Season summary: %d bets placed, %d wins, %d losses, %d skipped for a zero stake, %d failed.",
        summary["placed_bets"],
        summary["wins"],
        summary["losses"],
        summary["skipped_zero_stake"],
        summary["failed_bets"],
    )
    logger.info("Net profit (pnl): %.2f from a 1000.00 bankroll.", pnl(backtest.bet_history))
    logger.info("Return on investment (roi): %.4f per unit staked.", roi(backtest.bet_history))

    last_week = max(periods)
    logger.info("Model edges for matchweek %d, final ratings vs closing decimal prices:", last_week)
    for game in periods[last_week]:
        probability = calculate_probabilities(arena, game)
        wager_edge = edge(probability, game["winner_odds"])
        logger.info(
            "  %s at %.2f vs %s: P(win)=%.3f, edge=%+.3f",
            game["winner"],
            game["winner_odds"],
            game["loser"],
            probability,
            wager_edge,
        )


if __name__ == "__main__":
    main()
