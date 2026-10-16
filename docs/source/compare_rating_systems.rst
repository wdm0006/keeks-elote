Comparing rating systems
========================

.. function:: keeks_elote.model_evaluation.compare_rating_systems(data, systems=None, arena_kwargs=None)

   Scores every named rating system's ``run_and_project`` forecasts on one dataset.
   Each system gets a fresh arena from :func:`~keeks_elote.arena_factory.create_arena`,
   so no system sees another's state.

   :param data: Period-keyed games, as for ``Backtest.run_and_project``.
   :param systems: Rating-system names; defaults to all of them.
   :param arena_kwargs: Optional ``{system: kwargs}`` forwarded to ``create_arena``.
   :returns: One row per system -- ``system``, ``n``, ``skipped``, ``accuracy``,
             ``log_loss``, ``brier``, ``min_probability``, ``max_probability`` --
             sorted by ascending log loss, rows with no scored games after those,
             ``error`` rows last.
   :raises ValueError: On an unknown system name, before any run.

.. code-block:: python

   from keeks_elote import compare_rating_systems

   for row in compare_rating_systems(data):
       print(row)

A system that raises is recorded as ``{"system": ..., "error": ...}`` rather than
aborting the sweep.

Evaluation protocol
-------------------

The data is frozen and every system projects each period after the first from the
ratings built so far. There is no warm-up cutoff on scoring, so early periods are
predicted from almost no history. These figures are not comparable with
walk-forward or train/test-split numbers. Check ``min_probability`` and
``max_probability`` to see whether the log-loss clamp bound.
