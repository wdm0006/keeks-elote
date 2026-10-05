The full 1X2 book: home, draw, away
===================================

``examples/epl_1x2.py`` runs the multi-outcome flow
(:class:`keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest`) over a
draw-inclusive season, backtesting the whole three-leg book instead of the binary
backtest's one wager per game:

1. **Rating-driven probabilities.** The arena's expected score for each game is
   expanded into a full (home, draw, away) book by
   :func:`keeks_elote.multi_outcome_backtest.one_x_two_probabilities`, reserving a
   draw probability that peaks at rating parity (the Davidson tie term).
2. **Kelly sizing across the legs.** keeks'
   ``MultiOutcomeKellyCriterion`` splits the stake across the three legs, repriced
   per game with that game's own decimal odds.
3. **Simulated settlement.** A per-game one-trial
   ``RepeatedMultiOutcomeSimulator`` realizes exactly one leg from the model's own
   probabilities and settles the staked legs through the bankroll. The recorded
   scores rate the teams -- draws rate as draws -- but never decide a bet.
4. **The ledger.** Every game lands in ``bet_history`` with the book, the stake
   fractions, the absolute stakes, the realized leg, and the bankroll around it,
   so :func:`~keeks_elote.backtest.pnl` and :func:`~keeks_elote.backtest.roi`
   reconcile against the closing balance.

**The data is synthetic.** ``examples/data/epl_1x2_season.csv`` is a generated,
illustrative ten-week double round-robin (six teams, seeded Poisson scores,
bookmaker-style odds with a 4.5% margin) -- not a record of real results. The
committed binary EPL fixture excludes draws, which is exactly the outcome a 1X2
example needs, so none is fabricated under a real-world label. The run prices 17
of the 21 games (four have no complete set of prices and are rated but not bet),
realizes 9 home wins, 1 draw, and 7 away wins, and finishes at about 2,547 from a
1,000 bankroll -- a +26% return per unit staked, on a model settling its own
world. Treat it as a flow demonstration, not a result.

.. warning::

   Simulated results from a model, not a forecast and not investment advice.

Reproducing it
--------------

From a checkout of the repository, with the development environment installed
(``uv pip install -e ".[dev]"``):

.. code-block:: bash

   cd examples && ../.venv/bin/python epl_1x2.py

The settlement is seeded (``seed=42``), so a rerun replays the same season.
