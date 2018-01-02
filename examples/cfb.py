from elote import LambdaArena, EloCompetitor, ECFCompetitor, GlickoCompetitor, DWZCompetitor
from keeks import KellyCriterion, BankRoll, AllOnBest, Momentum, AllOnBestExpectedValue, AllOnMostMomentum, Blended
from keeks_elote import Backtest
import datetime
import json


# we already know the winner, so the lambda here is trivial
def func(a, b):
    return True


# the matchups are filtered down to only those between teams deemed 'reasonable', by me.
filt = {x for _, x in json.load(open('./data/cfb_teams_filtered.json', 'r')).items()}
games = json.load(open('./data/cfb_w_odds.json', 'r'))

# batch the games by week of year
games = [(datetime.datetime.strptime(x.get('date'), '%Y%m%d'), x) for x in games]
start_date = datetime.datetime(2017, 8, 21)
chunks = dict()
for week_no in range(1, 20):
    end_date = start_date + datetime.timedelta(days=7)
    chunks[week_no] = [v for k, v in games if k > start_date and k <= end_date]
    start_date = end_date

# set up the objects
arena = LambdaArena(func, base_competitor=GlickoCompetitor)
bank = BankRoll(10000, percent_bettable=0.5, max_draw_down=10e6, verbose=1)

# strategy = KellyCriterion(bankroll=bank, scale_bets=False, verbose=1)
# strategy = Momentum(bankroll=bank, verbose=1)
# strategy = AllOnBest(bankroll=bank, verbose=1)
# strategy = AllOnBestExpectedValue(bankroll=bank, verbose=1)
# strategy = AllOnMostMomentum(bankroll=bank, verbose=1)

strategy = Blended(
    bankroll=bank,
    strategies=[
        AllOnBest(bankroll=bank, verbose=1),
        AllOnBestExpectedValue(bankroll=bank, verbose=1),
        AllOnMostMomentum(bankroll=bank, verbose=1)
    ],
    verbose=1
)

backtest = Backtest(arena)
backtest.run_explicit(chunks, strategy, period_to_start_betting=4)
# backtest.run_and_project(chunks)