v0.1.0
======

First release. `keeks-elote` couples a rating system to a bankroll strategy: `elote` produces the
probabilities, market odds set the price, the gap between them is the edge, and a `keeks` strategy
turns that edge into a stake.

**Added:**
 * `RatingArena`, a protocol for any rating source that can run a tournament and report an expected score
 * `Backtest.run_explicit` and `Backtest.run_and_project`, which walk a period-keyed history, update
   ratings on settled results, then price the next period's bets from those ratings
 * American moneyline conversion in both directions, with invalid odds rejected before a strategy sees them
 * Bets sized from one snapshot of the opening bankroll, so wagers inside a period do not compound off each other
 * Stakes placed at the fraction the strategy actually quoted
 * A college football example (`examples/cfb.py`) running the whole stack on real season data

**Packaging:**
 * Requires Python 3.10 or newer, tested through 3.14
 * Requires `elote>=1.2.0` and `keeks>=0.3.0`
 * A mypy gate and ruff lint run in CI
