# Keeks-Elote

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<!-- Add badges for build status, coverage, etc. if available -->

A Python library integrating the [`elote`](https://elote.mcginniscommawill.com) rating system library and the [`keeks`](https://keeks.mcginniscommawill.com) bankroll management library to facilitate backtesting and evaluation of combined ranking and betting strategies.

## Purpose

The primary goal of `keeks-elote` is to provide a framework for simulating and analyzing the performance of different rating algorithms (like Elo, Glicko, etc.) when coupled with various bankroll management strategies (like Kelly Criterion, fixed betting, etc.). This allows users to explore how prediction accuracy from rating systems translates into profitability under different staking plans in competitive scenarios (e.g., sports betting, gaming).

## Why is this interesting? (Features)

*   **Integration:** Seamlessly combines rating generation (`elote`) with betting strategy simulation (`keeks`).
*   **Backtesting Framework:** Provides tools to run historical simulations on outcome data.
*   **Flexibility:** Supports multiple rating systems and bankroll management techniques available in the underlying libraries.
*   **Evaluation:** Enables analysis of strategy performance based on metrics like profit/loss, ROI, etc.
*   **Extensibility:** Designed to be potentially extended with custom rating models or betting strategies.

## Installation

You can install `keeks-elote` directly from the repo, soon we will publish it to PyPI.

```bash
git clone https://github.com/wdm0006/keeks-elote.git
cd keeks-elote
pip install -e .
```

For development, clone the repository and install in editable mode with development dependencies:

```bash
git clone https://github.com/wdm0006/keeks-elote.git
cd keeks-elote
pip install -e .[dev]
```

## How to Use It

The core idea is to use `elote` to generate ratings and predictions based on historical match/game data and then use `keeks` to simulate betting on those predictions according to a chosen bankroll strategy.

You provide historical outcomes as a `Dict[int, List[dict]]` keyed by period (e.g. week).
Each game dict needs `winner` and `loser` labels, plus optional `winner_odds`/`loser_odds`
in **American** odds (bets are only placed on games that include odds):

```python
from elote.arenas.lambda_arena import LambdaArena
from elote.competitors.glicko import GlickoCompetitor
from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

from keeks_elote import Backtest

# Historical outcomes, keyed by period (e.g. week). Ratings update from the
# known winner/loser; odds drive the simulated bets in later periods.
data = {
    1: [{"winner": "Alabama", "loser": "Auburn", "winner_odds": -150, "loser_odds": 130}],
    2: [{"winner": "Georgia", "loser": "Florida", "winner_odds": -200, "loser_odds": 175}],
    # ... more periods ...
}

# The arena generates ratings/predictions. The lambda reports the outcome of a
# matchup; since the data already records the winner, it is trivial here.
arena = LambdaArena(lambda a, b: True, base_competitor=GlickoCompetitor)

# The bankroll and a betting strategy from keeks.
bankroll = BankRoll(initial_funds=10000, percent_bettable=0.5, max_draw_down=10e6)
strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)

# Periods up to `period_to_start_betting` are dry runs that only build ratings;
# real bets begin after it. Returns the updated bankroll.
result = Backtest(arena).run_explicit(data, strategy, bankroll, period_to_start_betting=1)
print(result.total_funds)
```

See [`examples/cfb.py`](examples/cfb.py) for a complete end-to-end example using real
college-football data.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (if one exists, otherwise state MIT).
