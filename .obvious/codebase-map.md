# Codebase Map — keeks-elote

Folder-level overview (depth <= 2). Small library: ~950 LOC of package code, ~1,600 LOC of tests.

| Path | Kind | Purpose |
|---|---|---|
| `keeks_elote/` | Python package | The library. Public surface: `from keeks_elote import Backtest, GameRecord, MatchupTuple, ProjectionRecord, RatingArena, american_to_decimal, calculate_probabilities, create_arena, edge, load_csv, load_dataframe, pnl, prepare_data, roi, summarize_bet_history, to_decimal` (pinned by `tests/test_public_api.py`). |
| `keeks_elote/backtest.py` | module | Core of the library (500+ LOC): `Backtest` class with `run_explicit` (bankroll simulation) and `run_and_project` (returns `ProjectionRecord`s) — iterates period-keyed game data, updates elote ratings via the arena, sizes bets through keeks strategies, settles them, and records per-wager `bet_history`. Also American-to-decimal odds conversion and the matchup-tuple helper (score-aware for margin-of-victory rating systems). |
| `keeks_elote/arena_factory.py` | module | `create_arena`: maps a rating system's name (`RATING_SYSTEMS`, every elote single-system competitor) to its elote competitor class and returns a configured `LambdaArena`; `base_kwargs` configures the competitor, other kwargs forward to the arena; unknown names raise a `ValueError` listing the supported ones. |
| `keeks_elote/data_handling.py` | module | `prepare_data`: validates/cleans period-keyed input (drops games missing winner/loser labels, raises on wrong container types); `load_csv`/`load_dataframe`: build that input from a CSV file or a pandas-style DataFrame (required `period`/`winner`/`loser` columns, optional numeric odds/score columns, extra columns carried through; unplaceable periods raise, malformed rows drop with a warning). |
| `keeks_elote/model_evaluation.py` | module | `calculate_probabilities`: win probability for a game's winner via the arena's expected score. |
| `keeks_elote/rating_arena.py` | module | `RatingArena` Protocol (tournament + expected_score) — structural type for elote arenas, typed to elote's real matchup contract. |
| `keeks_elote/types.py` | module | Typed schemas: `GameRecord` (the game-record schema), `ProjectionRecord` (what `run_and_project` returns), `MatchupTuple` (the matchup shapes forwarded to an arena's `tournament`). |
| `tests/` | pytest suite | 197 tests: `test_backtest.py`, `test_backtest_settlement.py` (largest — bet settlement/history), `test_arena_factory.py` (create_arena round-trips every supported rating system), `test_data_handling.py` (prepare_data plus the load_csv/load_dataframe loaders, with CSV fixtures in `tests/fixtures/`), `test_examples.py` (runs every `examples/*.py` — the documented-examples CI gate), `test_cfb_example.py`, `test_integration_rating_systems.py` (Massey/Keener/Pythagorean through real elote arenas), `test_metrics.py`, `test_model_evaluation.py`, `test_packaging.py`, `test_public_api.py` (pins the package root's surface), `test_rating_arena.py`, `conftest.py`. |
| `examples/` | examples | `cfb.py` — end-to-end 2017 college-football backtest (Glicko + Kelly criterion); `epl.py` — the same flow over the real 2023-24 Premier League season (`load_csv` + `create_arena` + decimal odds + `edge` + `pnl`/`roi`). |
| `examples/data/` | data | CFB JSON datasets (~2 MB) incl. `cfb_w_odds.json` (games with moneylines) and team filters; `epl_2023_24.csv` — 2023-24 EPL results with Bet365 closing prices (football-data.co.uk), 298 decisive matches keyed by matchweek. |
| `.github/workflows/` | CI | `ci.yml`: pytest/mypy/ruff matrix on Python 3.10–3.14 + a `floor` job that installs runtime deps at `--resolution lowest-direct`. `publish-pypi.yml`: tag-triggered wheel/sdist build + trusted PyPI publish. |
| `Makefile` | build | uv-based targets: `install`, `test` (coverage), `typecheck` (mypy), `lint`/`check` (ruff), `format`, `clean`. |
| `pyproject.toml` | manifest | Metadata (v0.1.1), deps, dev extras, ruff (line-length 120) and mypy config. |
| `README.md` | docs | Purpose, install, usage quickstart, loading-your-own-data section, pointers to `examples/cfb.py` and `examples/epl.py`. |
| `CHANGELOG.md` | docs | Release history. |
