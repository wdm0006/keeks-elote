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
bankroll = BankRoll(initial_funds=10000, percent_bettable=0.5, max_transaction_loss=1.0)
strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost_rate=0.0)

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

Strategies that maintain state through keeks' `record_settlement(won, realized_returns)` hook --
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
input), `load_csv`/`load_dataframe` (build that input from a CSV file or a
DataFrame), `calculate_probabilities` (win probability from the arena),
`to_decimal` (either-format odds conversion, with `american_to_decimal` for
American-only input), `edge` (expected value per unit staked), `pnl`/`roi`
(ledger profit and per-unit-staked return), and `summarize_bet_history` (the
ledger aggregation behind `run_summary()`).

### Comparing configurations by forecast quality

Betting P&L is noisy and confounded by staking. To ask whether a rating system is well
calibrated, score its `run_and_project` forecasts against the recorded results with
`score_projections`, using a fresh arena per configuration:

```python
from keeks_elote import Backtest, create_arena, score_projections

for system in ("elo", "glicko"):
    projections = Backtest(create_arena(system)).run_and_project(data)
    print(system, score_projections(projections, data))
# {'n': ..., 'skipped': 0, 'accuracy': ..., 'log_loss': ..., 'brier': ...,
#  'min_probability': ..., 'max_probability': ...}
```

`log_loss` clamps probabilities at `epsilon` (default `1e-15`); `min_probability` and
`max_probability` are the raw extremes, so you can see whether the clamp bound. Projections
with no matching recorded game count in `skipped`; with nothing scored the metrics are `None`.

### Odds formats and value metrics

Game records accept prices in either format, and `to_decimal` converts any price explicitly:
a negative price or one of magnitude 1prices a wager's expected value per unit staked -- the comparison
between the model's win probability and the odds-implied one -- and `pnl`/`roi` net a
`bet_history` ledger into its profit and per-unit-staked return.

```python
from keeks_elote import edge, to_decimal

to_decimal(-110)   # 1.909... -- American
to_decimal(1.91)   # 1.91     -- decimal
edge(0.5, 2.1)     # 0.05 -- a half chance at 2.1 wins 5% per unit staked
```

### Loading your own data

`load_csv` and `load_dataframe` turn flat rows into the period-keyed dict the backtest
consumes: required `period`/`winner`/`loser` columns, optional `winner_odds`/`loser_odds`
prices and `winner_score`/`loser_score` margins, and any extra columns (dates, venues...)
carried through untouched. Row content is handled the way `prepare_data` handles it --
rows missing winner/loser labels are dropped with a warning and unparseable optional
numbers drop just that field -- while a row whose period is missing or not an integer
raises `ValueError` naming its line, so a corrupt schedule cannot load half-silently.
`load_dataframe` takes a pandas-style frame (pandas itself is not a dependency; any
object with `columns` and `to_dict(orient="records")` works):

```python
from keeks_elote import load_csv, load_dataframe

data = load_csv("data/epl_2023_24.csv")   # {1: [{...}, ...], 2: [...], ...}
data = load_dataframe(df)                 # same shape, from a DataFrame
```

For the 1X2 flow, `load_one_x_two_csv`/`load_one_x_two_dataframe` follow the same rules over
`period`, `home`, `away`, `home_score`, `away_score` (required) and
`home_odds`/`draw_odds`/`away_odds` (optional) columns; a row without labels or a numeric
score is dropped with a warning.

See [`examples/cfb.py`](examples/cfb.py) for a complete end-to-end example using real
college-football data, [`examples/cfb_weekly_portfolio.py`](examples/cfb_weekly_portfolio.py)
for the same season replayed as weekly portfolios -- each week's slate of games sized as one
joint allocation through keeks' allocation layer, next to the per-bet baseline,
[`examples/epl.py`](examples/epl.py) for the same flow over
the real 2023-24 Premier League season -- `load_csv`, `create_arena`, decimal odds,
`edge`, and the `pnl`/`roi` metrics -- and [`examples/epl_1x2.py`](examples/epl_1x2.py)
for the 1X2 flow below over a synthetic draw-inclusive season.

### The 1X2 (home / draw / away) flow

The binary backtest prices one wager per game because its records name a winner and a
loser. `keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest` backtests the whole
three-leg book -- home, draw, away -- through keeks' multi-outcome API: the arena's
expected score expands into a full (home, draw, away) book with a draw probability that
peaks at rating parity, a keeks multi-outcome strategy splits the stake across the legs
at each game's own prices, and each game settles against its recorded result -- the
`home_score`/`away_score` pair realizes the home, draw, or away leg, matching the binary
backtest. The same scores rate the teams (draws rate as draws, outcome 0.5). Pass
`settlement="simulated"` for the opt-in projection mode, which instead draws one leg per
game from the model's own book through `RepeatedMultiOutcomeSimulator`.

```python
from keeks.bankroll import BankRoll
from keeks.multi_outcome import MultiOutcomeKellyCriterion
from keeks_elote import MultiOutcomeBacktest, create_arena, pnl

backtest = MultiOutcomeBacktest(create_arena("elo"), draw_rate=0.25)
bankroll = BankRoll(initial_funds=1000.0, percent_bettable=1.0, max_transaction_loss=None)
backtest.run_explicit(
    data,                                       # period-keyed 1X2 game records
    MultiOutcomeKellyCriterion(payoffs=(2.0, 3.0, 3.0), loss=1.0),
    bankroll,
    period_to_start_betting=2,
)
pnl(backtest.bet_history)                       # net profit over the ledger
```

1X2 records name the sides positionally (`home`/`away`) and let the scores speak: `2-2`
is a draw, `0-1` an away win. The `home_odds`/`draw_odds`/`away_odds` prices are
optional per game and consumed only when all three are present; a game missing any
price is rated but not bet. `bet_history` records the book, the quoted stake fractions,
the absolute stakes, the realized leg, and the bankroll reads around every game, so
`pnl`/`roi` reconcile with the closing balance.

Recorded settlement debits every stake and credits the winning leg `payoff * stake`
(net `(payoff - 1) * stake`) directly on the bankroll, so `pnl`/`roi` are comparable with
the binary `Backtest`'s and a fully hedged fair book returns exactly the bankroll.

keeks 0.8.0 over-credited a 1X2 run's realized leg by one stake unit -- every `pnl`/`roi`
number it reported was inflated, and a fully hedged fair book printed a risk-free 25-50%
instead of breaking even. The defect was fixed in the 0.9.0 breaking sweep, so the
simulated path (`settlement="simulated"`) is exact under the same conventions too; the
fair-book characterization test asserts break-even and stays loud if the arithmetic ever
drifts again.

This flow uses keeks' `multi_outcome` module, installed with the package.

## Documentation

Full documentation — worked examples with plots and a hand-written API reference —
lives in `docs/` and is published to GitHub Pages on merge to master. To build it
locally:

```bash
uv pip install -r docs/requirements.txt
python -m sphinx -W --keep-going -b html docs/source docs/build/html
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
