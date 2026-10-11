"""Backtest a full 1X2 (home / draw / away) season through keeks' multi-outcome API.

The binary backtest in ``cfb.py`` prices a single wager per game because its
data names a winner and a loser. Real football markets offer three legs --
home, draw, away -- so this example runs the multi-outcome flow
(:class:`keeks_elote.multi_outcome_backtest.MultiOutcomeBacktest`):

1. Rating-driven probabilities: the arena's expected score for each game is
   expanded into a full (home, draw, away) book, reserving a draw
   probability that peaks at rating parity.
2. Kelly sizing: :class:`keeks.multi_outcome.MultiOutcomeKellyCriterion`
   splits the stake across the three legs, priced with each game's own odds.
3. Recorded settlement: each game settles on the leg its recorded scores
   imply (home win, draw, away win), debiting the stakes and crediting the
   winning leg, as the binary backtest does. ``settlement="simulated"`` is
   the opt-in alternative that draws the leg from the model's own book.
4. Ledger: every game lands in ``bet_history`` with the book, the stake
   fractions, the stakes, the realized leg, and the bankroll around it, so
   ``pnl`` and ``roi`` reconcile against the closing balance.

IMPORTANT -- the data is synthetic. ``./data/epl_1x2_season.csv`` is a
generated, illustrative ten-week double round-robin (six teams, seeded
Poisson scores, bookmaker-style odds with a 4.5% margin); it is not a record
of real results. The committed binary EPL fixture excludes draws, which is
exactly the outcome a 1X2 example needs, so none is fabricated here.

Run from the ``examples/`` directory so the relative data path resolves::

    cd examples && ../.venv/bin/python epl_1x2.py
"""

import logging
from collections import Counter

from keeks.bankroll import BankRoll

from keeks_elote import create_arena, load_one_x_two_csv, pnl, roi

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

STARTING_BANKROLL = 1000.0
DRAW_RATE = 0.25


def main() -> None:
    # The multi-outcome flow needs keeks >= 0.8.0, which is not on PyPI yet;
    # say so clearly instead of crashing (see the module docstring).
    try:
        from keeks.multi_outcome import MultiOutcomeKellyCriterion  # noqa: F401
    except ImportError:
        print(
            "This example needs the keeks multi-outcome API (keeks >= 0.8.0), which is not on PyPI yet.\n"
            "Install keeks from its git default branch, e.g.:\n"
            "    pip install 'keeks @ git+https://github.com/wdm0006/keeks.git'"
        )
        return

    from keeks_elote.multi_outcome_backtest import MultiOutcomeBacktest

    logger.info("Loading synthetic 1X2 season data...")
    periods = load_one_x_two_csv("./data/epl_1x2_season.csv")
    total_games = sum(len(games) for games in periods.values())
    logger.info("Loaded %d games across %d periods.", total_games, len(periods))

    arena = create_arena("elo")
    bankroll = BankRoll(initial_funds=STARTING_BANKROLL, percent_bettable=1.0, max_transaction_loss=None)
    # Payoffs here are the constructor's placeholder; the backtest reprices the
    # strategy per game with that game's decimal odds before staking it.
    strategy = MultiOutcomeKellyCriterion(payoffs=(2.0, 3.0, 3.0), loss=1.0)

    backtest = MultiOutcomeBacktest(arena, draw_rate=DRAW_RATE)
    logger.info("Running the 1X2 backtest (settled against the recorded results).")
    backtest.run_explicit(
        periods,
        strategy,
        bankroll,
        period_to_start_betting=2,
    )

    # --- Summary ---
    settled = [record for record in backtest.bet_history if record["stake"] > 0 and record["error"] is None]
    realized = Counter(record["won_leg"] for record in settled)
    print()
    print("=" * 60)
    print("1X2 season backtest (synthetic data) -- summary")
    print("=" * 60)
    print(f"Games considered: {len(backtest.bet_history)}; games staked: {len(settled)}")
    print(f"Realized legs: {realized.get(0, 0)} home wins, {realized.get(1, 0)} draws, {realized.get(2, 0)} away wins")
    print(f"Total staked: {sum(record['stake'] for record in settled):.2f}")
    print(f"Final bankroll: {bankroll.total_funds:.2f} (started {STARTING_BANKROLL:.2f})")
    print(f"PnL: {pnl(backtest.bet_history):.2f} | ROI: {roi(backtest.bet_history) * 100:.1f}%")
    print()
    print("First settled games (book -> stakes -> realized leg):")
    for record in settled[:3]:
        book = record["probabilities"]
        print(
            f"  period {record['period']}: {record['home']} vs {record['away']} -- "
            f"book ({book[0]:.3f}, {book[1]:.3f}, {book[2]:.3f}), "
            f"stakes ({record['stakes'][0]:.2f}, {record['stakes'][1]:.2f}, {record['stakes'][2]:.2f}), "
            f"won leg {record['won_leg']}, profit {record['profit']:+.2f}"
        )


if __name__ == "__main__":
    main()
