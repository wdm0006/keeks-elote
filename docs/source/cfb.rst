College football, one bet at a time
===================================

``examples/cfb.py`` runs the whole stack over a real season: the committed 2017
college-football fixture (``examples/data/cfb_w_odds.json``, filtered down to a
set of teams and carrying each game's American moneylines), Glicko ratings through
an elote arena, and the Kelly criterion sizing each game individually through the
per-bet engine (:class:`keeks_elote.backtest.Backtest`).

The games are batched into week-of-year chunks from their dates, so the schedule is
period-keyed the way the backtest expects. Four warm-up weeks rate the arena
before any money moves (``period_to_start_betting=4``), and from then on every
priced game -- either side, at its posted moneyline -- is a candidate the strategy
sizes against the bankroll. The run settles 441 bets over the season without a
failed or skipped candidate, and the bankroll's path through them is the
output: no chart, just the run's log line by line.

.. warning::

   Simulated results from a model, not a forecast and not investment advice.

Reproducing it
--------------

From a checkout of the repository, with the development environment installed
(``uv pip install -e ".[dev]"``):

.. code-block:: bash

   cd examples && ../.venv/bin/python cfb.py

The data files are committed next to the script, so nothing is fetched at run
time. To see the same season replayed with each week's slate sized as one joint
decision instead of game by game, see :doc:`cfb_weekly_portfolio`.
