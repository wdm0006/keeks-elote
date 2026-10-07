A real Premier League season, priced against closing lines
==========================================================

``examples/epl.py`` is the loaders-and-metrics tour over a real dataset: the 2023-24
English Premier League season with Bet365 closing prices (the committed
``examples/data/epl_2023_24.csv`` is from football-data.co.uk). It uses only what
the package root exports:

* :func:`~keeks_elote.data_handling.load_csv` turns the flat match rows into the
  period-keyed dict the backtest consumes -- one calendar matchweek per period,
  298 decisive matches (the season's 82 draws are excluded: the binary game
  schema has no third outcome).
* :func:`create_arena("elo") <keeks_elote.arena_factory.create_arena>`
  builds the rating arena in one line, and Elo ratings update from every recorded
  result as the season progresses.
* Every game carries decimal prices, so the per-bet engine
  (:class:`keeks_elote.backtest.Backtest`) prices each candidate through the
  decimal-odds path and the Kelly criterion sizes it; betting starts after
  matchweek 6.
* After the run, :func:`~keeks_elote.backtest.edge` re-prices the model's
  probabilities against the closing lines of the final matchweek (in-sample --
  the ratings have already seen those results), and
  :func:`~keeks_elote.backtest.pnl` / :func:`~keeks_elote.backtest.roi` net the
  settled ledger.

The honest headline of this example is that the model *loses*: against real
closing lines, a rating system's opinions are rarely the market's equal, and the
run's own summary says so -- 387 bets placed (155 won, 232 lost), a net profit of
about -600 from a 1,000 bankroll, and a return of roughly -0.05 per unit staked.
A backtest that only ever printed winning seasons would be hiding exactly this.

.. warning::

   Simulated results from a model, not a forecast and not investment advice.

Reproducing it
--------------

From a checkout of the repository, with the development environment installed
(``uv pip install -e ".[dev]"``):

.. code-block:: bash

   cd examples && ../.venv/bin/python epl.py

The CSV is committed next to the script, so nothing is fetched at run time.
