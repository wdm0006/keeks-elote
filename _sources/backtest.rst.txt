Backtest
========

The per-bet engine: ``keeks_elote.backtest`` prices a single wager per game and
settles it against the game's recorded result.

:class:`Backtest` walks a period-keyed schedule in order. Each period, it first
executes the bets priced in the previous period, then rates the period's recorded
results through the arena, then prices the next period's games against those
ratings -- so a week's pricing never sees its own results. Both sides of a priced
game are candidates (each at its posted price), every bet is sized from one
snapshot of the opening bankroll so wagers inside a period do not compound off
each other, and a period's total exposure is capped by the bankroll's
``percent_bettable``: requested stakes that exceed the budget are scaled down
proportionally, preserving the strategy's relative sizing.

The pricing is per-bet by fresh construction: each candidate is quoted through a
newly built strategy carrying that game's payoff and odds, so strategies never
carry state between pricing calls inside a period. Strategies that maintain state
through keeks' ``record_settlement(won, realized_returns)`` hook are notified of
every bet the run actually settles -- on the instance passed in -- so adaptive
strategies (``DynamicBankrollManagement``, for example) update as the run
progresses.

The Backtest class
------------------

.. class:: keeks_elote.backtest.Backtest(arena)

   Runs per-bet backtests over an elote arena.

   :param arena: An initialized arena satisfying the
                 :class:`~keeks_elote.rating_arena.RatingArena` protocol;
                 :func:`~keeks_elote.arena_factory.create_arena` builds one.

   .. attribute:: bet_history

      One dict per wager the run considered -- settled or not -- carrying
      ``period``, ``label``/``opponent``, the quoted ``fraction``, the ``stake``
      actually placed (after exposure scaling and any clamp against bettable
      funds), ``payoff`` (decimal odds minus one), ``won``, ``profit``,
      ``bankroll_after``, and the ``skipped_zero_stake`` / ``error`` flags for
      candidates that moved no money. Cleared at the start of each
      :meth:`run_explicit` call, so reusing a ``Backtest`` never mixes two runs.

   .. method:: run_explicit(data, strategy, bankroll, period_to_start_betting=3, price_bets_at_true_odds=True)

      Runs the backtest, period by period.

      :param data: Historical game data keyed by period; each game needs
                   ``winner``/``loser`` labels, plus optional
                   ``winner_odds``/``loser_odds`` prices in either American or
                   decimal format (detected per price -- see :func:`to_decimal`).
                   Games without odds are rated but not bet.
      :param strategy: A keeks binary strategy
                       (``keeks.binary_strategies.BaseStrategy``) that quotes the
                       fraction of the bankroll to stake.
      :param bankroll: A ``keeks.bankroll.BankRoll``, updated in place.
      :param period_to_start_betting: The last period that only builds ratings;
                                      real bets begin the period after it.
      :param price_bets_at_true_odds: Size each bet using its game-specific
                                      payoff. If false, the strategy's configured
                                      payoff is used for sizing (settlement always
                                      uses the game's actual odds).
      :returns: The updated bankroll.

   .. method:: run_summary()

      Condenses ``bet_history`` into the run's headline counts:
      ``total_candidates``, ``placed_bets``, ``failed_bets`` (with
      ``failure_reasons`` counted by error message), ``skipped_zero_stake``,
      ``wins``, ``losses``, and ``net_profit``. A systematically broken strategy
      reads as ``failed_bets: N`` -- never as an empty, plausible-looking run.

   .. method:: run_and_project(data)

      Rating-only run: walks the schedule, updates the arena, and returns one
      projection record per next-period game -- the projected period, the model's
      favored side, and its win probability (always >= 0.5). No betting.

Odds and ledger helpers
-----------------------

The module's helpers are also exported from the package root.

.. function:: keeks_elote.backtest.to_decimal(odds)

   Converts a price in either American or decimal format to decimal odds. The
   format is read off the value: negative values and values of 100 or more are
   American, values from 1.0 up to 100 are decimal, and values strictly between
   0 and 1.0 fit neither format and are rejected. Non-real, zero, and non-finite
   values raise ``TypeError``/``ValueError`` rather than converting.

.. function:: keeks_elote.backtest.american_to_decimal(american_odds)

   Converts strictly-American odds to decimal odds -- the explicit conversion for
   the one value range where format detection cannot help (American prices
   strictly between 0 and +100 are never quoted by real books).

.. function:: keeks_elote.backtest.edge(probability, decimal_odds)

   A wager's expected value per unit staked: ``p * (d - 1) - (1 - p)``. Positive
   exactly when the model's probability implies the price understates the true
   chance; ``edge(0.5, 2.1)`` is ``0.05``.

.. function:: keeks_elote.backtest.pnl(bet_history)

   Nets a ``bet_history`` ledger into its total profit. Failed evaluations and
   zero-stake candidates carry ``0.0``, so the whole book nets without
   special-casing.

.. function:: keeks_elote.backtest.roi(bet_history)

   The ledger's profit per unit staked (the ``pnl`` numerator over the sum of
   ``stake``); ``0.0`` when no money was staked.

.. function:: keeks_elote.backtest.summarize_bet_history(bet_history)

   The ledger aggregation behind :meth:`Backtest.run_summary` -- a pure function
   over the record schema, so caller-side aggregations agree with the run
   summary's definitions.
