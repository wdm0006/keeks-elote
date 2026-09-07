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

```bash
pip install keeks-elote
```

Or from source:

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
in **American or decimal** odds -- the format is detected per price (American when negative
or at least 100 in magnitude, decimal otherwise) -- and bets are only placed on games that
include odds:

```python
from keeks.bankroll import BankRoll
from keeks.binary_strategies.kelly import KellyCriterion

from keeks_elote import Backtest, create_arena

# Historical outcomes, keyed by period (e.g. week). Ratings update from the
# known winner/loser; odds drive the simulated bets in later periods.
data = {
    1: [{"winner": "Alabama", "loser": "Auburn", "winner_odds": -150, "loser_odds": 130}],
    2: [{"winner": "Georgia", "loser": "Florida", "winner_odds": -200, "loser_odds": 175}],
    # ... more periods ...
}

# The arena generates ratings and predictions from the game records. Every game's
# recorded winner is always forwarded to the ratings update, so the built-in
# comparison function is never asked to decide a result the data already knows.
arena = create_arena("glicko")

# The bankroll and a betting strategy from keeks.
bankroll = BankRoll(initial_funds=10000, percent_bettable=0.5, max_draw_down=1.0)
strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)

# Periods up to `period_to_start_betting` are dry runs that only build ratings;
# real bets begin after it. Returns the updated bankroll.
backtest = Backtest(arena)
result = backtest.run_explicit(data, strategy, bankroll, period_to_start_betting=1)
print(result.total_funds)

# Every wager the run settled is also recorded, so a comparison run can be read
# beyond its closing balance.
print(len(backtest.bet_history))
```

The closing `total_funds` conflates hit rate, stake sizing and how many bets were even
placed, so `run_explicit` also fills `Backtest.bet_history`: one dict per wager the run
considered, settled or not, carrying `period`, `label`, `opponent`, `fraction`, the
`stake` actually placed (after the period's exposure scaling and any clamp against
bettable funds), `payoff`, `won`, `profit` and `bankroll_after`. Candidates that moved
no money are recorded too, flagged with `skipped_zero_stake` or `error`, so every bet
the run considered is accounted for. The list is cleared at the start of each
`run_explicit` call, so reusing a `Backtest` never mixes two runs. Aggregations ship with
the package: `pnl(bet_history)` nets the run's profit and `roi(bet_history)` reports it per
unit staked, and anything more specific (hit rate, drawdown) stays one line of caller code
over the ledger.

Failures are part of that accounting: a strategy that raises while pricing a candidate
is recorded the moment it fails (`fraction` of `None` plus the error message), and
`Backtest.run_summary()` condenses the ledger into counts -- placed, failed with their
reasons, skipped, wins/losses and net profit -- so a systematically broken strategy
reads as `failed_bets: N`, never as an empty, plausible-looking run.

Strategies that maintain state through keeks' `record_result(won, return_pct)` hook --
`DynamicBankrollManagement`'s streak and volatility windows, for example -- are notified
of every bet the run actually settles, so their sizing adapts as the backtest progresses.
Strategies without the hook are unaffected, and stateful strategies are always notified
on the instance you passed in, even when each bet is priced by a freshly constructed
re-priced copy. The notification is skipped for candidates that moved no money (a zero
stake or a failed settlement), since there is no settled result to record.

### The one-liner and the rest of the public surface

`create_arena` maps a rating system's name to its elote competitor class, so the
arena setup is one line. Supported names: `bradley-terry`, `colley`, `dwz`,
`ecf`, `elo`, `glicko`, `glicko2`, `keener`, `massey`, `pythagorean`,
`trueskill`, and `whr`. Keyword arguments flow through: `base_kwargs` configures
the rating system's competitor (for example `{"initial_rating": 2100}`), and any
other keyword argument (elote's `func`, `initial_state`) is forwarded to the arena.

```python
from keeks_elote import create_arena

arena = create_arena("glicko")
```

An unknown name raises a `ValueError` listing the supported ones. The package
root also re-exports the functions the backtest itself runs on, so a single
import covers the whole flow: `prepare_data` (validates and cleans period-keyed
input), `calculate_probabilities` (win probability from the arena),
`to_decimal` (either-format odds conversion, with `american_to_decimal` for
American-only input), `edge` (expected value per unit staked), `pnl`/`roi`
(ledger profit and per-unit-staked return), and `summarize_bet_history` (the
ledger aggregation behind `run_summary()`).

### Odds formats and value metrics

Game records accept prices in either format, and `to_decimal` converts any price explicitly:
a negative price or one of magnitude 100 or more is read as American, anything from 1.0 up
to 100 as decimal. `edge` prices a wager's expected value per unit staked -- the comparison
between the model's win probability and the odds-implied one -- and `pnl`/`roi` net a
`bet_history` ledger into its profit and per-unit-staked return.

```python
from keeks_elote import edge, to_decimal

to_decimal(-110)   # 1.909... -- American
to_decimal(1.91)   # 1.91     -- decimal
edge(0.5, 2.1)     # 0.05 -- a half chance at 2.1 wins 5% per unit staked
```

See [`examples/cfb.py`](examples/cfb.py) for a complete end-to-end example using real
college-football data.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
