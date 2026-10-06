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
3. **Recorded settlement.** Each game settles on the leg its recorded scores
   imply (home win, draw, away win) -- the same convention as the binary
   backtest -- debiting the stakes and crediting the winning leg
   ``payoff * stake`` on the bankroll. ``settlement="simulated"`` is the
   opt-in alternative: keeks' one-trial simulator draws the leg from the
   model's own book instead.
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
realizes 9 home wins, 4 draws, and 4 away wins, and finishes at 664.35 from a
1,000 bankroll (PnL −335.65, ROI −14.3%): an Elo-derived, draw-blind book
staked by Kelly against a 4.5%-margin market loses across the season, which is
the honest outcome for a model that prices neither draws nor margin the way a
bookmaker does. Treat it as a flow demonstration, not a result.

.. warning::

   Simulated results from a model, not a forecast and not investment advice.

Reproducing it
--------------

From a checkout of the repository, with the development environment installed
(``uv pip install -e ".[dev]"``):

.. code-block:: bash

   cd examples && ../.venv/bin/python epl_1x2.py

The run is fully deterministic: settlement is recorded by default, so a rerun
replays the same season with no seed at all.
