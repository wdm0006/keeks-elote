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
