Unreleased
==========

**Added:**
 * `edge(probability, decimal_odds)` computes a wager's expected value per unit staked --
   `p * (d - 1) - (1 - p)` -- so a model's win probability can be priced against the odds
   directly (`edge(0.5, 2.1)` is `0.05`).
 * `to_decimal(odds)` converts prices from either American or decimal format: a negative
   price or one of magnitude 100 or more is read as American, a price from 1.0 up to 100 as
   decimal, and a price that fits neither (between 0 and 1) is rejected. The backtest
   pricing path now reads every `winner_odds`/`loser_odds` value through it, so game records
   accept either format wherever American odds were accepted before; a price that fits
   neither format is skipped with a warning instead of being priced as a tiny American odd.
 * `pnl(bet_history)` and `roi(bet_history)` report a ledger's net profit and
   per-unit-staked return alongside `summarize_bet_history`.

v0.2.0
======

The first version published to PyPI — the v0.1.0 and v0.1.1 tags were cut but their trusted-publishing
runs were rejected before upload, so everything since v0.1.0 ships in this one distribution. It carries
the correctness fixes the release was gated on: no silent wrong stakes, no re-decided games, no silent
failures.

**Added:**
 * `bet_history` records the wagers a backtest actually placed — the stake, the settled profit, and
   the bankroll after settlement — so a run can be audited bet by bet.
 * Failed strategy evaluations are recorded too: each failure lands in `bet_history` with its reason,
   and `run_summary()` reports placed, failed, and skipped counts.
 * The glue surface is typed against real contracts: game and matchup records, structured
   projections, and exports from the package root. Integration tests run real elote arenas
   (Massey, Keener, Pythagorean) instead of test doubles.
 * Dependency governance: runtime bounds (`keeks>=0.3.0,<0.8`, `elote>=1.3.0,<1.4`), a committed
   `uv.lock`, and a weekly drift workflow that installs keeks and elote from their git default
   branches and runs the suite, attributing any failure to the dependency that drifted.

**Fixed:**
 * Every bet is priced through a freshly constructed strategy. Repricing through a shared instance
   let stateful strategies carry state between pricing calls inside a period and quietly request
   stakes they would never have asked for fresh.
 * Games are rated on the result that was recorded, not re-decided by the rating system, and settled
   outcomes are announced to stateful strategies — post-settlement state now agrees with what
   actually happened.

**Packaging:**
 * The publish workflow declares a named `pypi` GitHub environment, giving the PyPI trusted
   publisher a deterministic claim set. The earlier tag publishes failed as `invalid-publisher`
   because no matching publisher was registered on PyPI.

v0.1.1
======

**Added:**
 * Game scores are forwarded to the rating arena, so margin-aware rating systems (Massey,
   Keener, Pythagorean) see the margin and not just who won. A game carrying `winner_score`
   and `loser_score` is passed through as elote's full matchup tuple; a game without them
   keeps the plain two-element form the win/loss systems expect. A score that is missing,
   unparseable, or that contradicts the recorded winner (a `0-0` placeholder, for instance)
   falls back to the result alone with a warning, rather than failing the run or reporting a
   tie margin that never happened.

**Fixed:**
 * A period's *total* exposure is now capped by `percent_bettable`, rather than each bet
   being clamped against the funds still live when it is placed. A strategy quoting a
   fraction per game cannot know how many other games it is being asked about, so a
   confident week routinely requested several times the bankroll; the earliest games then
   consumed everything and the rest were staked from the scraps. Requested stakes that
   exceed the budget are scaled down proportionally, preserving the relative sizing the
   strategy asked for.

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
