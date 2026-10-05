Weekly-portfolio backtest
=========================

The portfolio engine: ``keeks_elote.portfolio_backtest`` sizes each period's
slate of games as one joint decision, where
:class:`~keeks_elote.backtest.Backtest` sizes its bets one at a time. It is the
shape a football week actually presents -- N simultaneous games, one bankroll
decision, one settlement batch -- and it consumes keeks 0.9's allocation layer:
the week's arena probabilities and posted American moneylines become a
``keeks.allocation.BinaryBetsModel``, an allocator
(``keeks.allocation.BaseAllocationStrategy``) weights the whole slate at once,
and a one-trial ``keeks.allocation.AllocationSimulator`` settles the week
batch-net through the shared bankroll.

The two engines are deliberately siblings over identical inputs -- same schedule,
same ratings, same bankroll conventions -- so a per-bet run and a
weekly-portfolio run over one fixture can be compared side by side;
``examples/cfb_weekly_portfolio.py`` is that comparison
(:doc:`cfb_weekly_portfolio`).

Conventions
-----------

**One bet per game, winner side.** Each game contributes a single option: the
recorded winner's side at its posted moneyline, sized by the arena's win
probability for that team. Backing the loser side too would put two perfectly
anti-correlated options in a model whose correlation-aware allocators assume
independence, so the slate stays one bet per game.

**An allocator per week.** The caller supplies a factory -- a callable from the
week's ``BinaryBetsModel`` to the allocator that sizes it (see
:data:`AllocatorFactory`) -- because the slate's width changes from week to week
as games gain, lose, or carry no usable moneyline, and every shipped allocator
fixes its weight-vector width at construction from that week's moments or
scenarios. Stateful (online) allocators keep their state across weeks through
the forwarded ``update_bankroll`` hook only when the factory returns the same
instance each week; moment-based factories construct a fresh allocator per week,
which is the common case.

**One trial per week.** The simulator runs ``trials=1`` per week, so the
bankroll's batch-net settlement convention evaluates exactly once per week: the
week's stakes are ``bettable_funds * weight`` per bet, and the whole batch nets
to a single bankroll transaction.

**Seeding.** With ``seed`` set, week *t* of the schedule (in sorted period order,
warm-up weeks included) settles from a simulator seeded ``seed + t`` -- the
per-stream pattern :mod:`~keeks_elote.multi_outcome_backtest` uses per game -- so
a seeded run replays bit-exactly, and changing ``period_to_start_betting`` does
not shift any week's stream. With ``seed=None`` no replay is promised.

**Time-stamped rating.** When every game in the schedule carries a parseable
``date``, rating is time-stamped from those dates: a week is rated in kickoff
order, and Glicko's rating-deviation decay follows the fixture's calendar instead
of the wall clock. Any undated game switches the whole run to elote's default
wall-clock rating.

The WeeklyPortfolioBacktest class
---------------------------------

.. class:: keeks_elote.portfolio_backtest.WeeklyPortfolioBacktest(arena)

   Backtests rating-driven betting with each period's slate sized jointly.

   :param arena: An initialized arena satisfying the
                 :class:`~keeks_elote.rating_arena.RatingArena` protocol;
                 :func:`~keeks_elote.arena_factory.create_arena` builds one.

   .. attribute:: bet_history

      The last run's weekly ledger (cleared at the start of each
      :meth:`run_explicit` call) -- one dict per settled week, the same records
      the method returns. See :meth:`run_explicit` for the schema.

   .. method:: run_explicit(data, allocator_factory, bankroll, transaction_cost_rate=0.0, period_to_start_betting=0, seed=None)

      Runs the weekly-portfolio backtest, period by period. Per period, in
      order: price the period's bettable games against the ratings as they stand
      (the period's own results are not yet rated, so nothing leaks), settle the
      week's slate as one portfolio decision through the shared bankroll, then
      rate the period's recorded results. Periods up to and including
      ``period_to_start_betting`` are rating-only warm-up.

      :param data: Historical game data keyed by period; each game needs
                   ``winner``/``loser`` labels, and ``winner_ml`` (an American
                   price, string or numeric) makes the game bettable when it
                   converts to a usable decimal price. Games without a usable
                   price are rated but not bet.
      :param allocator_factory: Maps the week's
                                ``keeks.allocation.BinaryBetsModel`` to the
                                allocator that sizes it -- see
                                :data:`AllocatorFactory`.
      :param bankroll: A ``keeks.bankroll.BankRoll``, updated in place.
      :param transaction_cost_rate: The per-unit-staked fee folded into every
                                    bet's win and loss returns in the week's
                                    model. Defaults to 0.0 (fee-free).
      :param period_to_start_betting: The last period that only builds ratings.
                                      Defaults to 0.
      :param seed: Base seed for the per-week settlement streams. ``None``
                   promises no replay.
      :returns: The run's weekly ledger -- one dict per settled week with the
                slate ``bets`` (the backed label and opponent, the arena's win
                probability, the decimal-odds price), the allocator's
                ``weights``, the per-bet ``stakes`` and their total ``stake``
                (the denominator :func:`~keeks_elote.backtest.roi` uses), the
                settled ``returns``/``won`` flags, the week's ``profit`` and the
                ``bankroll_before``/``bankroll_after`` reads, and the
                ``skipped_zero_stake``/``error`` flags for weeks that moved no
                money.

The allocator-factory contract
------------------------------

.. data:: keeks_elote.portfolio_backtest.AllocatorFactory

   Maps the week's joint-return model to the allocator that sizes it:
   ``Callable[[BinaryBetsModel], BaseAllocationStrategy]``. A callable, because
   the slate's width changes from week to week -- every shipped allocator fixes
   its weight-vector width at construction from that week's moments or
   scenarios. ``examples/cfb_weekly_portfolio.py`` ships two: a mean-variance
   factory over the model's exact moments, and a mean-CVaR factory over seeded
   scenario draws.
