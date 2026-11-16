Comparing staking configurations
================================

.. function:: keeks_elote.comparison.compare_backtests(data, configurations, *, period_to_start_betting=3, price_bets_at_true_odds=True)

   Runs ``Backtest.run_explicit`` once per configuration over the same binary
   (winner/loser) schedule and returns one row per configuration, in input order.

   :param data: Period-keyed games, as for ``Backtest.run_explicit``.
   :param configurations: Insertion-ordered ``{label: factory}``. Each factory takes no
                          arguments and returns a fresh ``(arena, strategy, bankroll)``.
   :param period_to_start_betting: Shared warm-up threshold.
   :param price_bets_at_true_odds: Shared sizing option.
   :returns: Rows with ``name``, ``opening_funds``, ``closing_funds``, ``pnl``, ``roi``,
             ``summary`` (``Backtest.run_summary``, including ``failed_bets`` and
             ``failure_reasons``) and ``bet_history`` (that run's ledger). An empty
             mapping returns ``[]``.
   :raises RuntimeError: If a factory or run raises; the message names the configuration
                         and the original exception is chained as the cause.
   :raises TypeError: For a non-mapping, a non-callable factory, or a factory that does
                      not return a 3-tuple.

Factories own construction. The arena, strategy and bankroll all mutate during a run,
so every factory call must return independent objects; the helper does not copy or
rebuild them. Each factory is called once per invocation.

.. code-block:: python

   from keeks.bankroll import BankRoll
   from keeks.binary_strategies import FractionalKellyCriterion, KellyCriterion

   from keeks_elote import compare_backtests, create_arena

   def build(strategy_factory):
       return lambda: (
           create_arena("glicko"),
           strategy_factory(),
           BankRoll(initial_funds=1000.0, percent_bettable=0.5, max_transaction_loss=1.0),
       )

   rows = compare_backtests(
       data,
       {
           "kelly": build(lambda: KellyCriterion(payoff=1.0, loss=1.0, transaction_cost_rate=0.0)),
           "half kelly": build(
               lambda: FractionalKellyCriterion(payoff=1.0, loss=1.0, transaction_cost_rate=0.0, fraction=0.5)
           ),
       },
       period_to_start_betting=3,
   )
   for row in rows:
       print(row["name"], row["closing_funds"], row["pnl"], row["roi"], row["summary"]["failed_bets"])

Evaluation settings
-------------------

There is no ranking. Returns under different bankroll, ``percent_bettable`` or
staking settings are not interchangeable, and one schedule says nothing about
statistical significance. Check ``summary["failed_bets"]`` and ``failure_reasons``
before reading a row: candidates that could not be priced or settled are in the
ledger but moved no money. The shared ``period_to_start_betting`` and
``price_bets_at_true_odds`` apply to every row.

1X2 and weekly portfolio runs
-----------------------------

``compare_one_x_two_backtests(data, configurations, *, draw_rate=0.25,
period_to_start_betting=3, seed=None, settlement="recorded")`` and
``compare_portfolio_backtests(data, configurations, *, transaction_cost_rate=0.0,
period_to_start_betting=0, seed=None)`` follow the same contract: one fresh
factory call per configuration, rows in input order, no ranking, and a
``RuntimeError`` naming the configuration on failure. The 1X2 factory returns
``(arena, multi_outcome_strategy, bankroll)`` and settles against recorded scores by
default; the portfolio factory returns ``(arena, allocator_factory, bankroll)``.
Rows carry ``name``, ``opening_funds``, ``closing_funds``, ``pnl``, ``roi`` and the
engine's own ``bet_history``. They have no ``summary``, because
``summarize_bet_history`` rejects those ledger schemas.

.. code-block:: python

   rows = compare_portfolio_backtests(
       data,
       {"mean-variance": lambda: (create_arena("elo"), my_allocator_factory, BankRoll(1000.0))},
       seed=7,
   )
