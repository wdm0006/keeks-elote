"""Side-by-side comparison of binary staking configurations."""

import logging
from typing import Any, Callable, Dict, List, Mapping, Tuple

from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote.backtest import Backtest, pnl, roi
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord

logger = logging.getLogger(__name__)

ConfigurationFactory = Callable[[], Tuple[RatingArena, BaseStrategy, BankRoll]]


def compare_backtests(
    data: Dict[int, List[GameRecord]],
    configurations: Mapping[str, ConfigurationFactory],
    *,
    period_to_start_betting: int = 3,
    price_bets_at_true_odds: bool = True,
) -> List[Dict[str, Any]]:
    """Runs ``Backtest.run_explicit`` once per configuration over the same schedule.

    Each value of ``configurations`` is a zero-argument factory returning a fresh
    ``(arena, strategy, bankroll)`` tuple. The factories own construction: the arena,
    strategy and bankroll all mutate during a run, so every call must return
    independent objects (never one you already returned or still hold). Each factory
    is called exactly once per invocation, and this helper neither copies arbitrary
    strategy objects nor infers how to build them.

    Every configuration is settled by the existing engine under the same
    ``period_to_start_betting`` and ``price_bets_at_true_odds``. Rows come back in the
    mapping's order, with no ranking: returns under different bankroll, exposure or
    staking settings are not interchangeable, and one schedule is not a significance
    test. Binary (winner/loser) schedules only.

    :param data: Period-keyed games, as for ``Backtest.run_explicit``.
    :param configurations: Insertion-ordered ``{label: factory}``; empty returns ``[]``.
    :param period_to_start_betting: Warm-up threshold forwarded to ``run_explicit``.
    :param price_bets_at_true_odds: Forwarded to ``run_explicit``.
    :returns: One dict per configuration: ``name``, ``opening_funds`` and
              ``closing_funds`` (the bankroll's ``total_funds`` before and after),
              ``pnl`` and ``roi`` (the existing helpers over the ledger), ``summary``
              (``Backtest.run_summary``, including ``failed_bets`` and
              ``failure_reasons`` for candidates that could not be priced or settled)
              and ``bet_history`` (that run's ledger).
    :raises TypeError: If ``configurations`` is not a mapping, a value is not callable,
                       or a factory does not return a 3-tuple. Checked per
                       configuration when it runs, except the first two, which are
                       checked before any factory is called.
    :raises RuntimeError: If a factory or run raises; the message names the
                          configuration and the original exception is the ``__cause__``.
                          No row is fabricated for a failed configuration.
    """
    if not isinstance(configurations, Mapping):
        raise TypeError("configurations must be a mapping of label to zero-argument factory")
    for name, factory in configurations.items():
        if not callable(factory):
            raise TypeError(f"configuration {name!r}: factory must be callable")

    rows: List[Dict[str, Any]] = []
    for name, factory in configurations.items():
        try:
            built = factory()
        except Exception as exc:
            raise RuntimeError(f"configuration {name!r} failed: factory raised {exc!r}") from exc
        if not isinstance(built, tuple) or len(built) != 3:
            raise TypeError(f"configuration {name!r}: factory must return an (arena, strategy, bankroll) tuple")
        arena, strategy, bankroll = built

        try:
            opening_funds = bankroll.total_funds
            backtest = Backtest(arena)
            backtest.run_explicit(
                data,
                strategy,
                bankroll,
                period_to_start_betting=period_to_start_betting,
                price_bets_at_true_odds=price_bets_at_true_odds,
            )
            closing_funds = bankroll.total_funds
        except Exception as exc:
            raise RuntimeError(f"configuration {name!r} failed: run raised {exc!r}") from exc

        ledger = list(backtest.bet_history)
        rows.append(
            {
                "name": name,
                "opening_funds": opening_funds,
                "closing_funds": closing_funds,
                "pnl": pnl(ledger),
                "roi": roi(ledger),
                "summary": backtest.run_summary(),
                "bet_history": ledger,
            }
        )
        logger.info("Compared configuration %r: closing funds %.2f", name, closing_funds)
    return rows
