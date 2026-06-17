import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def prepare_data(data: Dict[int, List[Dict[str, Any]]]) -> Dict[int, List[Dict[str, Any]]]:
    """Prepares and validates the input data structure.

    Validation rules:

    * ``data`` must be a ``dict`` keyed by period; anything else raises
      :class:`TypeError`.
    * Each game must be a ``dict`` containing both ``winner`` and ``loser``
      keys. Games that are not dicts or are missing either label are dropped
      with a warning (consistent with how :class:`~keeks_elote.backtest.Backtest`
      skips unlabeled games).

    Well-formed input is returned unchanged (the same object), so the
    passthrough contract is preserved. A new structure is only built when one
    or more malformed games are dropped.

    :param data: Raw historical game data, expected to be keyed by period.
    :type data: Dict[int, List[Dict[str, Any]]]
    :return: The validated data with any malformed games removed.
    :rtype: Dict[int, List[Dict[str, Any]]]
    :raises TypeError: If ``data`` is not a dict.
    """
    logger.info("Preparing data...")
    logger.debug(f"Input data type: {type(data)}")
    if not isinstance(data, dict):
        raise TypeError(f"prepare_data expected a dict keyed by period, got {type(data).__name__}.")
    logger.debug(f"Data has {len(data)} periods.")

    cleaned: Dict[int, List[Dict[str, Any]]] = {}
    dropped = 0
    for period, games in data.items():
        valid_games = []
        for game in games:
            if not isinstance(game, dict) or game.get("winner") is None or game.get("loser") is None:
                logger.warning(f"Period {period}: dropping game with missing winner/loser labels: {game}")
                dropped += 1
                continue
            valid_games.append(game)
        cleaned[period] = valid_games

    logger.info("Data preparation complete.")
    # Preserve the passthrough contract (same object) when nothing was dropped.
    return data if dropped == 0 else cleaned
