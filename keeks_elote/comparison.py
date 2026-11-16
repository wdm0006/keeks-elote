"""Side-by-side comparison of binary staking configurations."""

import logging
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote.backtest import Backtest, pnl, roi
from keeks_elote.multi_outcome_backtest import MultiOutcomeBacktest
from keeks_elote.portfolio_backtest import WeeklyPortfolioBacktest
from keeks_elote.rating_arena import RatingArena
from keeks_elote.types import GameRecord, OneXTwoGameRecord

logger = logging.getLogger(__name__)

ConfigurationFactory = Callable[[], Tuple[RatingArena, BaseStrategy, BankRoll]]
PortfolioConfigurationFactory = Callable[[], Tuple[RatingArena, Callable[..., Any], BankRoll]]


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

    def execute(arena: Any, strategy: Any, bankroll: BankRoll) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        backtest = Backtest(arena)
        backtest.run_explicit(
            data,
            strategy,
            bankroll,
            period_to_start_betting=period_to_start_betting,
            price_bets_at_true_odds=price_bets_at_true_odds,
        )
        return backtest.bet_history, {"summary": backtest.run_summary()}

    return _compare(configurations, execute, "(arena, strategy, bankroll)")


def compare_one_x_two_backtests(
    data: Dict[int, List[OneXTwoGameRecord]],
    configurations: Mapping[str, ConfigurationFactory],
    *,
    draw_rate: float = 0.25,
    period_to_start_betting: int = 3,
    seed: Optional[int] = None,
    settlement: str = "recorded",
) -> List[Dict[str, Any]]:
    """Runs ``MultiOutcomeBacktest.run_explicit`` once per configuration over one 1X2 schedule.

    Same contract as :func:`compare_backtests`: each factory returns a fresh
    ``(arena, strategy, bankroll)`` with a keeks multi-outcome strategy, is called once
    per invocation, rows come back in input order and are never ranked. Settlement
    defaults to the recorded scores; ``seed`` and ``settlement`` are forwarded as given.

    :returns: One dict per configuration: ``name``, ``opening_funds``, ``closing_funds``,
              ``pnl``, ``roi`` and ``bet_history`` (the engine's 1X2 ledger). There is no
              ``summary``: ``summarize_bet_history`` does not accept this schema.
    :raises RuntimeError: If a factory or run raises, naming the configuration.
    """

    def execute(arena: Any, strategy: Any, bankroll: BankRoll) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        backtest = MultiOutcomeBacktest(arena, draw_rate=draw_rate)
        backtest.run_explicit(
            data,
            strategy,
            bankroll,
            period_to_start_betting=period_to_start_betting,
            seed=seed,
            settlement=settlement,
        )
        return backtest.bet_history, {}

    return _compare(configurations, execute, "(arena, strategy, bankroll)")


def compare_portfolio_backtests(
    data: Dict[int, List[GameRecord]],
    configurations: Mapping[str, PortfolioConfigurationFactory],
    *,
    transaction_cost_rate: float = 0.0,
    period_to_start_betting: int = 0,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Runs ``WeeklyPortfolioBacktest.run_explicit`` once per configuration over one schedule.

    Same contract as :func:`compare_backtests`, but each factory returns a fresh
    ``(arena, allocator_factory, bankroll)``. ``seed`` is forwarded so a seeded
    comparison is reproducible.

    :returns: One dict per configuration: ``name``, ``opening_funds``, ``closing_funds``,
              ``pnl``, ``roi`` and ``bet_history`` (the weekly ledger). There is no
              ``summary``: ``summarize_bet_history`` does not accept this schema.
    :raises RuntimeError: If a factory or run raises, naming the configuration.
    """

    def execute(arena: Any, allocator_factory: Any, bankroll: BankRoll) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        backtest = WeeklyPortfolioBacktest(arena)
        backtest.run_explicit(
            data,
            allocator_factory,
            bankroll,
            transaction_cost_rate=transaction_cost_rate,
            period_to_start_betting=period_to_start_betting,
            seed=seed,
        )
        return backtest.bet_history, {}

    return _compare(configurations, execute, "(arena, allocator_factory, bankroll)")


def _compare(
    configurations: Mapping[str, Callable[[], Tuple[Any, Any, BankRoll]]],
    execute: Callable[[Any, Any, BankRoll], Tuple[List[Dict[str, Any]], Dict[str, Any]]],
    shape: str,
) -> List[Dict[str, Any]]:
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
            raise TypeError(f"configuration {name!r}: factory must return an {shape} tuple")
        arena, second, bankroll = built

        try:
            opening_funds = bankroll.total_funds
            history, extra = execute(arena, second, bankroll)
            closing_funds = bankroll.total_funds
        except Exception as exc:
            raise RuntimeError(f"configuration {name!r} failed: run raised {exc!r}") from exc

        ledger = list(history)
        row: Dict[str, Any] = {
            "name": name,
            "opening_funds": opening_funds,
            "closing_funds": closing_funds,
            "pnl": pnl(ledger),
            "roi": roi(ledger),
        }
        row.update(extra)
        row["bet_history"] = ledger
        rows.append(row)
        logger.info("Compared configuration %r: closing funds %.2f", name, closing_funds)
    return rows
