Multi-outcome backtest
======================

The 1X2 engine: ``keeks_elote.multi_outcome_backtest`` backtests the whole
home / draw / away book of three-way markets through keeks' multi-outcome API,
where :class:`~keeks_elote.backtest.Backtest` prices a single binary wager per
game.

Two semantics differ from the binary backtest and are worth naming. **Settlement
is simulated, not recorded**: a categorical draw realizes one leg from the model's
own probabilities, while the recorded scores rate the competitors but never decide
a settled bet -- this flow is a projection exercise, pricing the strategy the
model's own world. And **payoffs are decimal odds**: keeks' multi-outcome contract
quotes each leg's payoff as decimal odds (a winning leg pays ``payoff * stake``,
stake included), while the binary backtest's ledger records ``payoff`` as decimal
odds minus one -- the same word means different things one module away.

Rating updates treat a draw as a draw: the arena receives the recorded result as
outcome 1.0 / 0.0 / 0.5 from the home perspective, cross-checked against the score
pair. keeks 0.9.0 fixed the multi-outcome settlement over-credit that inflated
every 1X2 ``pnl``/``roi`` number (a fully hedged fair book used to print a
risk-free 25-50% instead of breaking even), so 1X2 P&L is directly comparable to
the binary backtest's.

Leg order
---------

.. data:: keeks_elote.multi_outcome_backtest.LEGS

   The fixed leg order used everywhere: ``("home", "draw", "away")``. The
   positional index of a probability, payoff, stake fraction, or settlement
   return is fixed by this tuple.

Building the book
-----------------

.. function:: keeks_elote.multi_outcome_backtest.one_x_two_probabilities(p_home, draw_rate=0.25)

   Builds a 1X2 book from a rating-derived, draw-blind win probability.

   The draw probability follows the Davidson tie term,
   ``draw_rate * 4 * p * (1 - p)`` -- peaking at ``draw_rate`` when the sides are
   rated evenly and fading toward the extremes (favorites draw less) -- and the
   remaining mass is split in proportion to the original win probability. The
   three returned probabilities always sum to one, so a fully priced book leaves
   no void mass on which the market refunds.

   :param p_home: The arena's expected score for the home side, in ``[0, 1]``.
   :param draw_rate: The draw probability at rating parity, in ``[0, 1]``.
                     Roughly a quarter is typical for association football.
   :returns: The ``(home, draw, away)`` probability book, in :data:`LEGS` order,
             summing to one.

The MultiOutcomeBacktest class
------------------------------

.. class:: keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest(arena, draw_rate=0.25)

   Backtests 1X2 betting over an elote arena. Each game carries its own
   probability book and its own prices, so each game gets a freshly constructed
   strategy (per-game repricing, the pattern the binary backtest established) and
   its own one-trial simulator instance seeded ``seed + game_index`` in schedule
   order -- a seeded run replays identically; ``seed=None`` promises no replay.

   :param arena: An initialized arena satisfying the
                 :class:`~keeks_elote.rating_arena.RatingArena` protocol;
                 :func:`~keeks_elote.arena_factory.create_arena` builds one.
   :param draw_rate: The draw probability the pricing model assumes at rating
                     parity; see :func:`one_x_two_probabilities`.

   .. attribute:: bet_history

      One dict per game the run considered, cleared at the start of each run:
      ``period``/``home``/``away``, the model's ``probabilities`` book and the
      game's decimal-odds ``payoffs`` (in :data:`LEGS` order), the quoted
      ``fractions`` per leg, the absolute ``stakes`` and their total ``stake``
      (the denominator :func:`~keeks_elote.backtest.roi` uses), the realized
      leg's index ``won_leg`` (``None`` for a void round), the signed net
      ``returns`` per leg, ``profit`` and the ``bankroll_before`` /
      ``bankroll_after`` reads around settlement, and the
      ``skipped_zero_stake`` / ``error`` flags. ``BankRoll`` reads are rounded
      to cents, so ``profit`` agrees with the exact settlement returns only to
      within that cent.

   .. method:: run_explicit(data, strategy, bankroll, period_to_start_betting=3, seed=None)

      Runs the 1X2 backtest, period by period: price and settle every game
      against the ratings as they stand (when the period is a betting period),
      then rate the period's recorded results -- wins, losses, and draws --
      through the arena. Periods up to and including
      ``period_to_start_betting`` are rating-only warm-up.

      :param data: Historical 1X2 game data keyed by period; each game needs
                   ``home``/``away`` labels and ``home_score``/``away_score``,
                   with optional ``home_odds``/``draw_odds``/``away_odds``
                   prices (in either format) that make the game bettable when
                   all three are present.
      :param strategy: A keeks multi-outcome strategy
                       (``keeks.multi_outcome.BaseMultiOutcomeStrategy``) that
                       splits a stake across the legs; ABC strategies are
                       repriced per game by fresh construction, and stateful
                       strategies receive ``update_bankroll`` and
                       ``record_settlement`` on the instance passed in, once
                       per settled game.
      :param bankroll: A ``keeks.bankroll.BankRoll``, updated in place.
      :param period_to_start_betting: The last period that only builds ratings.
      :param seed: Base seed for the per-game settlement streams; each game's
                   simulator is seeded ``seed + game_index`` in schedule order.
      :returns: The bankroll, updated with the run's settlements.

      Games that cannot be rated (missing labels or scores) or cannot be priced
      (a leg with no price, or a price that fits no format) are warned about and
      skipped: they produce no ledger entry and, when unratable, no rating update
      either.
