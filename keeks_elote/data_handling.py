import csv
import logging
import math
import numbers
import operator
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union, cast

from keeks_elote.types import GameRecord

logger = logging.getLogger(__name__)


def prepare_data(data: Dict[int, List[Any]]) -> Dict[int, List[GameRecord]]:
    """Prepares and validates the input data structure.

    Validation rules:

    * ``data`` must be a ``dict`` keyed by period; anything else raises
      :class:`TypeError`.
    * Each period must contain a ``list`` of games; anything else raises
      :class:`TypeError`.
    * Each game must be a ``dict`` containing both ``winner`` and ``loser``
      keys. Games that are not dicts or are missing either label are dropped
      with a warning (consistent with how :class:`~keeks_elote.backtest.Backtest`
      skips unlabeled games).

    Well-formed input is returned unchanged (the same object), so the
    passthrough contract is preserved. A new structure is only built when one
    or more malformed games are dropped.

    The element type is ``Any`` because this is the raw, untrusted boundary of the
    package: well-formed callers may declare their data as
    ``Dict[int, List[GameRecord]]``, but anything that arrives here is inspected at
    runtime rather than trusted.

    :param data: Raw historical game data, expected to be keyed by period.
    :type data: Dict[int, List[Any]]
    :return: The validated data with any malformed games removed, typed as the
        :class:`~keeks_elote.types.GameRecord` schema.
    :rtype: Dict[int, List[GameRecord]]
    :raises TypeError: If ``data`` is not a dict or a period does not contain a list.
    """
    logger.info("Preparing data...")
    logger.debug(f"Input data type: {type(data)}")
    if not isinstance(data, dict):
        raise TypeError(f"prepare_data expected a dict keyed by period, got {type(data).__name__}.")
    logger.debug(f"Data has {len(data)} periods.")

    cleaned: Dict[int, List[Dict[str, Any]]] = {}
    dropped = 0
    for period, games in data.items():
        if not isinstance(games, list):
            raise TypeError(
                f"prepare_data expected period {period} to contain a list of games, got {type(games).__name__}."
            )
        valid_games = []
        for game in games:
            if not isinstance(game, dict) or game.get("winner") is None or game.get("loser") is None:
                logger.warning(f"Period {period}: dropping game with missing winner/loser labels: {game}")
                dropped += 1
                continue
            valid_games.append(game)
        cleaned[period] = valid_games

    logger.info("Data preparation complete.")
    # Validation checked exactly what GameRecord requires (winner/loser present and
    # non-None); the schema's other keys are optional, so the survivors satisfy it
    # even though they are carried as plain dicts.
    prepared = data if dropped == 0 else cleaned
    return cast(Dict[int, List[GameRecord]], prepared)


# --- Data loaders ------------------------------------------------------------
#
# load_csv and load_dataframe turn flat rows (a CSV file, a pandas-style
# DataFrame) into the period-keyed dict prepare_data consumes. They are lenient
# where a row can be dropped without hiding the damage and strict where the
# structure would otherwise lie: row content follows prepare_data's rules
# (missing labels drop the row with a warning; unparseable optional numbers
# drop just that field), while a row whose period cannot be parsed has nowhere
# to go and raises instead of silently vanishing from the schedule.

#: Columns every input must carry; the rest of the GameRecord schema is optional.
_REQUIRED_COLUMNS = ("period", "winner", "loser")

#: Optional columns parsed as numbers when present.
_NUMERIC_COLUMNS = ("winner_odds", "loser_odds", "winner_score", "loser_score")


def _is_missing(value: Any) -> bool:
    """True for the shapes an absent cell takes: ``None``, blank strings, NaN, and pandas' NA/NaT."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        return math.isnan(float(value))
    # pandas' NA and NaT singletons are not numbers.Real, so the NaN branch above
    # cannot see them; pandas is an optional dependency, so they are recognized by
    # their type names rather than an import.
    if type(value).__name__ in ("NAType", "NaTType"):
        return True
    return False


def _parse_period(value: Any, where: str) -> int:
    """Parses a row's period, raising :class:`ValueError` when it cannot be placed."""
    if _is_missing(value):
        raise ValueError(f"{where}: period is missing.")
    if isinstance(value, bool):
        raise ValueError(f"{where}: period must be an integer, got {value!r}.")
    if isinstance(value, numbers.Integral):
        return operator.index(value)  # exact Python int from any integral scalar (numpy included)
    if isinstance(value, numbers.Real) and float(value).is_integer():
        return int(float(value))
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError(f"{where}: period must be an integer, got {value!r}.") from None


def _parse_numeric(value: Any, where: str) -> Optional[float]:
    """Parses one optional numeric cell, or ``None`` when it is absent or unusable.

    An absent cell (``None``, blank, NaN) is quiet -- the field is simply not set.
    A value that is present but unparseable or non-finite is warned about and
    dropped, keeping the game ratable on its recorded result, the same degradation
    the backtest applies to unparseable scores.
    """
    if _is_missing(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (numbers.Real, str)):
        logger.warning(f"{where}: expected a number, dropping the field (got {value!r}).")
        return None
    try:
        number = float(value)
    except ValueError:
        logger.warning(f"{where}: could not parse {value!r} as a number, dropping the field.")
        return None
    if not math.isfinite(number):
        logger.warning(f"{where}: {value!r} is not finite, dropping the field.")
        return None
    return number


def _record_from_row(row: Mapping[str, Any], where: str) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Normalizes one raw row into ``(period, record)``, or ``None`` when it is dropped.

    The recorded ``winner``/``loser`` labels are the ground truth every later stage
    rates and bets on, so a row without both is dropped with a warning -- the same
    rule :func:`prepare_data` applies. Unknown columns (dates, venues...) pass
    through onto the record untouched, the way the extra keys in the CFB example
    data do; :func:`prepare_data` and the backtest ignore them.
    """
    period = _parse_period(row.get("period"), where)
    winner = row.get("winner")
    loser = row.get("loser")
    if isinstance(winner, str):
        winner = winner.strip()
    if isinstance(loser, str):
        loser = loser.strip()
    if _is_missing(winner) or _is_missing(loser):
        logger.warning(f"{where}: dropping row with missing winner/loser labels (winner={winner!r}, loser={loser!r}).")
        return None

    record: Dict[str, Any] = {"period": period, "winner": winner, "loser": loser}
    for column in _NUMERIC_COLUMNS:
        number = _parse_numeric(row.get(column), f"{where} ({column})")
        if number is not None:
            record[column] = number
    for key, value in row.items():
        if key in record or key in _NUMERIC_COLUMNS or _is_missing(value):
            continue
        record[key] = value
    return period, record


def _require_columns(columns: List[str], source: str) -> None:
    """Raises :class:`ValueError` when the input lacks a required column."""
    missing = [column for column in _REQUIRED_COLUMNS if column not in columns]
    if missing:
        raise ValueError(f"{source}: missing required column(s) {', '.join(missing)}; found {columns}.")


def _periods_from_rows(rows: Iterable[Tuple[str, Mapping[str, Any]]]) -> Dict[int, List[Dict[str, Any]]]:
    """Groups ``(where, row)`` pairs into the period-keyed structure, in input order."""
    periods: Dict[int, List[Dict[str, Any]]] = {}
    for where, row in rows:
        parsed = _record_from_row(row, where)
        if parsed is None:
            continue
        period, record = parsed
        periods.setdefault(period, []).append(record)
    return periods


def load_csv(path: Union[str, os.PathLike]) -> Dict[int, List[GameRecord]]:
    """Loads period-keyed game data from a CSV file.

    The file needs ``period``, ``winner`` and ``loser`` columns; optional
    ``winner_odds``/``loser_odds`` prices and ``winner_score``/``loser_score``
    margins are parsed as numbers, and any further columns (dates, venues...)
    pass through onto the record untouched. The result is the period-keyed dict
    :func:`prepare_data` consumes -- integer period keys whose values are lists
    of dicts satisfying the :class:`~keeks_elote.types.GameRecord` schema --
    with rows grouped in file order, so it feeds
    :meth:`~keeks_elote.backtest.Backtest.run_explicit` directly.

    Lenient where a row can be dropped without hiding the damage, strict where
    the structure would lie:

    * rows without recorded winner/loser labels are dropped with a warning,
      the same rule :func:`prepare_data` applies;
    * a value that will not parse as one of the optional numbers drops just
      that field (with a warning) and keeps the game;
    * a row whose ``period`` is missing or not an integer raises
      :class:`ValueError` naming the file line -- a row with no place to go
      would silently vanish from the schedule.

    :param path: Path of the CSV file (UTF-8; a leading BOM is tolerated).
    :type path: Union[str, os.PathLike]
    :return: The loaded data, keyed by period, ready for :func:`prepare_data`
        or :meth:`~keeks_elote.backtest.Backtest.run_explicit`.
    :rtype: Dict[int, List[GameRecord]]
    :raises ValueError: If a required column is missing, or a row's period is
        missing or not an integer.
    """
    with open(path, "r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, restval="")
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        _require_columns(fieldnames, str(path))
        rows: List[Tuple[str, Mapping[str, Any]]] = []
        for row in reader:
            where = f"{path} line {reader.line_num}"
            overflow = row.pop(None, None)  # fields beyond the header, if the row is ragged
            if overflow is not None:
                logger.warning(f"{where}: row has more fields than the header; ignoring the extras {overflow!r}.")
            rows.append((where, row))
    return cast(Dict[int, List[GameRecord]], _periods_from_rows(rows))


def load_dataframe(df: Any) -> Dict[int, List[GameRecord]]:
    """Loads period-keyed game data from a DataFrame.

    A thin adapter over pandas -- or any object with the same two members: a
    ``columns`` attribute and a ``to_dict(orient="records")`` method; pandas
    itself is not a dependency of this package, so the frame is typed as
    ``Any`` rather than trusted to exist. Column semantics, leniency, and
    error behavior are exactly :func:`load_csv`'s: required ``period``,
    ``winner`` and ``loser`` columns, optional numeric odds/score columns,
    and anything else carried through. Blank cells -- ``None`` or ``NaN``
    after ``to_dict`` -- count as absent, so optional fields can simply be
    left empty in the frame.

    :param df: A ``pandas.DataFrame`` shaped like :func:`load_csv`'s input file.
    :type df: Any
    :return: The loaded data, keyed by period, ready for :func:`prepare_data`
        or :meth:`~keeks_elote.backtest.Backtest.run_explicit`.
    :rtype: Dict[int, List[GameRecord]]
    :raises ValueError: If a required column is missing, or a row's period is
        missing or not an integer.
    """
    _require_columns([str(column).strip() for column in df.columns], "data frame")
    rows = [(f"row {index}", row) for index, row in enumerate(df.to_dict(orient="records"))]
    return cast(Dict[int, List[GameRecord]], _periods_from_rows(rows))
