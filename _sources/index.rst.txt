Welcome to Keeks-Elote
======================

Keeks-Elote couples the `elote <https://elote.mcginniscommawill.com>`_ rating-system
library with the `keeks <https://keeks.mcginniscommawill.com>`_ bankroll-management
library, so rating-driven predictions can be backtested against real betting
strategies. The ratings produce win probabilities from the results as they stand,
the posted prices set what a win pays, and the gap between the model and the market
-- the edge -- is turned into a stake by a keeks strategy.

The package covers both betting shapes. The per-bet engine
(:class:`keeks_elote.backtest.Backtest`) sizes each game individually: a strategy
quotes the fraction of the bankroll to stake on one game at a time, and every game
settles on its own recorded result. The portfolio engine
(:class:`keeks_elote.portfolio_backtest.WeeklyPortfolioBacktest`) sizes a whole
period's slate of games as one joint decision through keeks' allocation layer, and
:class:`keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest` prices the full
home / draw / away book of three-way markets through keeks' multi-outcome API.
Arenas for the twelve supported rating systems are built in one line by
:func:`keeks_elote.arena_factory.create_arena`.

.. warning::

   This library is for educational purposes only. It is not intended to provide
   investment, legal, or tax advice. Every worked example here replays a
   simulation, and its bankrolls, edges, and returns are properties of the model --
   never predictions about real money. Always be responsible and consult with a
   professional before applying these strategies to real-world betting scenarios.

Installation
------------

.. code-block:: bash

   pip install keeks-elote

or, with uv:

.. code-block:: bash

   uv pip install keeks-elote

Quickstart
----------

A period-keyed history, an arena, a bankroll, a strategy -- the whole flow in one
pass. Periods up to ``period_to_start_betting`` are dry runs that only build
ratings; real bets begin after that:

.. code-block:: python

   from keeks.bankroll import BankRoll
   from keeks.binary_strategies.kelly import KellyCriterion

   from keeks_elote import Backtest, create_arena

   # Historical outcomes, keyed by period (e.g. week). Ratings update from the
   # known winner/loser; odds drive the simulated bets in later periods.
   data = {
       1: [{"winner": "Alabama", "loser": "Auburn", "winner_odds": -150, "loser_odds": 130}],
       2: [{"winner": "Georgia", "loser": "Florida", "winner_odds": -200, "loser_odds": 175}],
   }

   arena = create_arena("glicko")

   bankroll = BankRoll(initial_funds=10000, percent_bettable=0.5, max_transaction_loss=1.0)
   strategy = KellyCriterion(payoff=1.0, loss=1.0, transaction_cost_rate=0.0)

   backtest = Backtest(arena)
   result = backtest.run_explicit(data, strategy, bankroll, period_to_start_betting=1)
   print(result.total_funds)          # the closing bankroll
   print(len(backtest.bet_history))   # every wager the run considered

The closing ``total_funds`` conflates hit rate, stake sizing, and how many bets
were even placed, so :meth:`~keeks_elote.backtest.Backtest.run_explicit` also fills
``backtest.bet_history``: one record per wager the run considered, settled or not,
carrying the stake, the profit, and the bankroll after settlement. Candidates that
moved no money are recorded too (``skipped_zero_stake`` or ``error``), and
:func:`~keeks_elote.backtest.pnl` and :func:`~keeks_elote.backtest.roi` net that
ledger into its profit and its per-unit-staked return.

.. toctree::
   :caption: Examples
   :maxdepth: 1

   cfb
   epl
   epl_1x2
   cfb_weekly_portfolio

.. toctree::
   :caption: API Reference
   :maxdepth: 1

   backtest
   multi_outcome_backtest
   arena_factory
   portfolio_backtest
