"""Replay the 2017 CFB season two ways: one bet at a time vs one slate at a time.

This is the weekly-portfolio sibling of ``cfb.py`` -- same committed fixture,
same week batching, same Glicko ratings, same warm-up and bankroll -- so the two
approaches can be compared over identical inputs:

- ``per-bet Kelly`` sizes each game individually through
  :class:`keeks_elote.backtest.Backtest` (the ``cfb.py`` path), and
- the weekly-portfolio arms size each week's slate of winner-side bets jointly
  through :class:`keeks_elote.portfolio_backtest.WeeklyPortfolioBacktest`, one
  joint-return model and one allocator decision per week.

Each arm gets a fresh arena and bankroll so the runs cannot influence one
another; the summary table and the bankroll-path chart below are the
comparison. Run it from the ``examples/`` directory::

    ../.venv/bin/python cfb_weekly_portfolio.py

and find the chart under ``output/``.
"""

import datetime
import json
import logging
import math
import os

import matplotlib
import numpy as np
from elote.arenas.lambda_arena import LambdaArena
from elote.competitors.glicko import GlickoCompetitor
from keeks.allocation import MeanCVaR, MeanVariance, bankroll_paths
from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

from keeks_elote import Backtest, WeeklyPortfolioBacktest

# Headless rendering: the chart is written to output/, never shown.
matplotlib.use("Agg")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

STARTING_FUNDS = 10000
PERCENT_BETTABLE = 0.5
MAX_TRANSACTION_LOSS = 1.0
PERIOD_TO_START_BETTING = 4
SIMULATOR_SEED = 42
SCENARIO_SEED = 1337


# we already know the winner, so the lambda here is trivial
def func(a, b):
    return True


def normalize_moneylines(games):
    """Normalizes the fixture's American moneylines to numeric ``winner_odds``/``loser_odds``."""
    normalized_games = []
    for game in games:
        normalized_game = game.copy()
        try:
            winner_odds = float(game["winner_ml"])
            loser_odds = float(game["loser_ml"])
            if not math.isfinite(winner_odds) or not math.isfinite(loser_odds):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            normalized_game.pop("winner_odds", None)
            normalized_game.pop("loser_odds", None)
        else:
            normalized_game["winner_odds"] = int(winner_odds) if winner_odds.is_integer() else winner_odds
            normalized_game["loser_odds"] = int(loser_odds) if loser_odds.is_integer() else loser_odds
        normalized_games.append(normalized_game)
    return normalized_games


def weekly_chunks(games):
    """Batches the season's games into week-of-year chunks (the ``cfb.py`` batching)."""
    dated = [(datetime.datetime.strptime(game.get("date"), "%Y%m%d"), game) for game in games]
    start_date = datetime.datetime(2017, 8, 21)
    chunks = {}
    for week_no in range(1, 20):
        end_date = start_date + datetime.timedelta(days=7)
        chunks[week_no] = [game for date, game in dated if start_date < date <= end_date]
        start_date = end_date
    return chunks


def max_drawdown(path):
    """Computes the largest peak-to-trough loss of a bankroll path (the number behind the drawdown plot)."""
    path = np.asarray(path, dtype=float)
    peaks = np.maximum.accumulate(path)
    return float(np.max((peaks - path) / peaks))


def run_per_bet(chunks):
    """Runs the ``cfb.py`` baseline: Kelly sizes each game individually."""
    arena = LambdaArena(func, base_competitor=GlickoCompetitor)
    bank = BankRoll(
        initial_funds=STARTING_FUNDS, percent_bettable=PERCENT_BETTABLE, max_transaction_loss=MAX_TRANSACTION_LOSS
    )
    backtest = Backtest(arena)
    backtest.run_explicit(
        chunks,
        KellyCriterion(payoff=1.0, loss=1.0, transaction_cost_rate=0.0),
        bank,
        period_to_start_betting=PERIOD_TO_START_BETTING,
    )
    return bank


def run_portfolio(chunks, allocator_factory):
    """Runs one weekly-portfolio arm: the allocator sizes each week's slate jointly."""
    arena = LambdaArena(func, base_competitor=GlickoCompetitor)
    bank = BankRoll(
        initial_funds=STARTING_FUNDS, percent_bettable=PERCENT_BETTABLE, max_transaction_loss=MAX_TRANSACTION_LOSS
    )
    backtest = WeeklyPortfolioBacktest(arena)
    history = backtest.run_explicit(
        chunks,
        allocator_factory,
        bank,
        transaction_cost_rate=0.0,
        period_to_start_betting=PERIOD_TO_START_BETTING,
        seed=SIMULATOR_SEED,
    )
    logger.info("Weekly portfolio run settled %d weeks.", len(history))
    return bank


def mean_variance_factory(risk_aversion=1.0):
    """Builds a factory sizing each week's slate with mean-variance over the model's exact moments."""

    def factory(model):
        mean, covariance = model.moments()
        return MeanVariance(mean, covariance, risk_aversion=risk_aversion)

    return factory


def mean_cvar_factory(n_scenarios=500, tail_alpha=0.05, seed=SCENARIO_SEED):
    """Builds a factory sizing each week's slate with mean-CVaR over seeded scenario draws."""
    state = {"week": 0}

    def factory(model):
        rng = np.random.default_rng(seed + state["week"])
        state["week"] += 1
        return MeanCVaR(model.sample(n_scenarios, rng), tail_alpha=tail_alpha)

    return factory


def summarize(name, bank):
    """One summary row per arm: where the bankroll ended and how it got there."""
    path = bank.history
    weeks = len(path) - 1
    final = path[-1]
    total_return = final / STARTING_FUNDS - 1.0
    growth_per_week = (final / STARTING_FUNDS) ** (1.0 / weeks) - 1.0 if weeks else 0.0
    return {
        "approach": name,
        "final": final,
        "total_return": total_return,
        "growth_per_week": growth_per_week,
        "max_drawdown": max_drawdown(path),
    }


def print_summary(rows):
    """Prints the summary table comparing the arms."""
    header = f"{'approach':<38} {'final bankroll':>15} {'total return':>13} {'growth/wk':>11} {'max drawdown':>13}"
    logger.info("Summary\n%s", header)
    logger.info("%s", "-" * len(header))
    for row in rows:
        logger.info(
            "%-38s %15.2f %12.1f%% %10.3f%% %12.1f%%",
            row["approach"],
            row["final"],
            row["total_return"] * 100.0,
            row["growth_per_week"] * 100.0,
            row["max_drawdown"] * 100.0,
        )


def main():
    # the matchups are filtered down to only those between teams deemed 'reasonable', by me.
    logger.info("Loading data...")
    _filt = {x for _, x in json.load(open("./data/cfb_teams_filtered.json", "r")).items()}
    games = normalize_moneylines(json.load(open("./data/cfb_w_odds.json", "r")))
    logger.info("Loaded %d games.", len(games))

    logger.info("Batching games by week...")
    chunks = weekly_chunks(games)
    logger.info("Created %d weekly chunks.", len(chunks))

    logger.info("Arm 1: per-bet Kelly (the cfb.py path)...")
    per_bet_bank = run_per_bet(chunks)

    logger.info("Arm 2: weekly portfolio, mean-variance allocator...")
    mean_variance_bank = run_portfolio(chunks, mean_variance_factory())

    logger.info("Arm 3: weekly portfolio, mean-CVaR allocator...")
    mean_cvar_bank = run_portfolio(chunks, mean_cvar_factory())

    rows = [
        summarize("per-bet Kelly", per_bet_bank),
        summarize("weekly portfolio (mean-variance)", mean_variance_bank),
        summarize("weekly portfolio (mean-CVaR)", mean_cvar_bank),
    ]
    print_summary(rows)

    logger.info("Rendering the bankroll-path comparison chart...")
    axes = bankroll_paths(
        {
            "per-bet Kelly": per_bet_bank,
            "weekly portfolio (mean-variance)": mean_variance_bank,
            "weekly portfolio (mean-CVaR)": mean_cvar_bank,
        }
    )
    os.makedirs("output", exist_ok=True)
    figure = axes.get_figure()
    figure.savefig("output/cfb_weekly_portfolio.png", dpi=150, bbox_inches="tight")
    logger.info("Saved output/cfb_weekly_portfolio.png")


if __name__ == "__main__":
    main()
