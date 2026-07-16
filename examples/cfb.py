import datetime
import json
import logging  # Add logging configuration
import math

from elote.arenas.lambda_arena import LambdaArena

# from elote.competitors.elo import EloCompetitor
# from elote.competitors.ecf import ECFCompetitor
from elote.competitors.glicko import GlickoCompetitor

# from elote.competitors.dwz import DWZCompetitor
from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

# Remove unavailable imports
# from keeks.binary_strategies.simple import AllOnBest
# from keeks import Momentum
# from keeks import AllOnBestExpectedValue
# from keeks import AllOnMostMomentum
# from keeks import Blended
from keeks_elote import Backtest

# --- Add Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# --- End Logging Setup ---


# we already know the winner, so the lambda here is trivial
def func(a, b):
    return True


def normalize_moneylines(games):
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


def main():
    # the matchups are filtered down to only those between teams deemed 'reasonable', by me.
    logger.info("Loading data...")
    _filt = {x for _, x in json.load(open("./data/cfb_teams_filtered.json", "r")).items()}
    games = normalize_moneylines(json.load(open("./data/cfb_w_odds.json", "r")))
    logger.info(f"Loaded {len(games)} games.")

    # batch the games by week of year
    logger.info("Batching games by week...")
    games = [(datetime.datetime.strptime(x.get("date"), "%Y%m%d"), x) for x in games]
    start_date = datetime.datetime(2017, 8, 21)
    chunks = {}
    for week_no in range(1, 20):
        end_date = start_date + datetime.timedelta(days=7)
        chunks[week_no] = [v for k, v in games if k > start_date and k <= end_date]
        start_date = end_date
    logger.info(f"Created {len(chunks)} weekly chunks.")

    # set up the objects
    logger.info("Setting up Arena and Bankroll...")
    arena = LambdaArena(func, base_competitor=GlickoCompetitor)
    bank = BankRoll(initial_funds=10000, percent_bettable=0.5, max_draw_down=10e6)

    logger.info("Setting up Strategy (using KellyCriterion)...")
    # NOTE: KellyCriterion in keeks 0.3.0+ takes payoff, loss, and transaction_cost
    # These are nominal values as the actual odds are calculated per-bet in the backtest
    strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)

    logger.info("Initializing Backtest...")
    backtest = Backtest(arena)
    logger.info("Running explicit backtest...")
    # Pass the bankroll object separately now
    backtest.run_explicit(chunks, strategy, bank, period_to_start_betting=4)
    logger.info("Backtest finished.")


if __name__ == "__main__":
    main()
