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
3. Simulated settlement: a per-game ``RepeatedMultiOutcomeSimulator``
   realizes exactly one leg per game from the model's own probabilities and
   settles the staked legs through the bankroll; the recorded scores rate the
   teams but never decide a bet.
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

import csv
import logging
import math
from collections import Counter
from typing import Any, Dict, List

from keeks.bankroll import BankRoll

from keeks_elote import create_arena, pnl, roi

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

STARTING_BANKROLL = 1000.0
DRAW_RATE = 0.25


def _as_float(value: Any, field: str, line: int) -> float:
    """Parses one fixture field as a finite float, failing loudly otherwise."""
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Line {line}: field {field!r} is not a number: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Line {line}: field {field!r} is not finite: {value!r}")
    return parsed


def load_one_x_two_season(path: str) -> Dict[int, List[Dict[str, Any]]]:
    """Loads the CSV fixture into period-keyed game records.

    Each row needs ``period``, ``home``, ``away``, ``home_score``,
    ``away_score``, and the three odds columns. Scores and odds are parsed as
    floats here; a malformed fixture is an error, not something to guess
    around.
    """
    periods: Dict[int, List[Dict[str, Any]]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            home, away = row.get("home"), row.get("away")
            if not home or not away:
                raise ValueError(f"Line {line}: game record is missing home/away labels: {row!r}")
            game = {
                "home": home,
                "away": away,
                "home_score": _as_float(row.get("home_score"), "home_score", line),
                "away_score": _as_float(row.get("away_score"), "away_score", line),
            }
            for key in ("home_odds", "draw_odds", "away_odds"):
                game[key] = _as_float(row.get(key), key, line)
            period = int(_as_float(row.get("period"), "period", line))
            periods.setdefault(period, []).append(game)
    return periods


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
    periods = load_one_x_two_season("./data/epl_1x2_season.csv")
    total_games = sum(len(games) for games in periods.values())
    logger.info("Loaded %d games across %d periods.", total_games, len(periods))

    arena = create_arena("elo")
    bankroll = BankRoll(initial_funds=STARTING_BANKROLL, percent_bettable=1.0, max_draw_down=None)
    # Payoffs here are the constructor's placeholder; the backtest reprices the
    # strategy per game with that game's decimal odds before staking it.
    strategy = MultiOutcomeKellyCriterion(payoffs=(2.0, 3.0, 3.0), loss=1.0)

    backtest = MultiOutcomeBacktest(arena, draw_rate=DRAW_RATE)
    logger.info("Running the 1X2 backtest (settlement is simulated from the model's own book).")
    backtest.run_explicit(
        periods,
        strategy,
        bankroll,
        period_to_start_betting=2,
        seed=42,
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
