# Codebase Map — keeks-elote

Folder-level overview (depth <= 2). Small library: ~590 LOC of package code, ~1,280 LOC of tests.

| Path | Kind | Purpose |
|---|---|---|
| `keeks_elote/` | Python package | The library. Public surface: `from keeks_elote import Backtest`. |
| `keeks_elote/backtest.py` | module | Core of the library (493 LOC): `Backtest` class and `run_explicit` — iterates period-keyed game data, updates elote ratings via the arena, sizes bets through keeks strategies, settles them, and records per-wager `bet_history`. Also American-to-decimal odds conversion and matchup-tuple helpers (score-aware for margin-of-victory rating systems). |
| `keeks_elote/data_handling.py` | module | `prepare_data`: validates/cleans period-keyed input (drops games missing winner/loser labels, raises on wrong container types). |
| `keeks_elote/model_evaluation.py` | module | `calculate_probabilities`: win probability for a game's winner via the arena's expected score. |
| `keeks_elote/rating_arena.py` | module | `RatingArena` Protocol (tournament + expected_score) — structural type for elote arenas. |
| `tests/` | pytest suite | 71 tests: `test_backtest.py`, `test_backtest_settlement.py` (largest — bet settlement/history), `test_cfb_example.py`, `test_examples.py`, `test_data_handling.py`, `test_model_evaluation.py`, `test_packaging.py`, `test_rating_arena.py`, `conftest.py`. |
| `examples/` | example | `cfb.py` — end-to-end 2017 college-football backtest (Glicko + Kelly criterion). |
| `examples/data/` | data | CFB JSON datasets (~2 MB) incl. `cfb_w_odds.json` (games with moneylines) and team filters. |
| `.github/workflows/` | CI | `ci.yml`: pytest/mypy/ruff matrix on Python 3.10–3.14 + a `floor` job that installs runtime deps at `--resolution lowest-direct`. `publish-pypi.yml`: tag-triggered wheel/sdist build + trusted PyPI publish. |
| `Makefile` | build | uv-based targets: `install`, `test` (coverage), `typecheck` (mypy), `lint`/`check` (ruff), `format`, `clean`. |
| `pyproject.toml` | manifest | Metadata (v0.1.1), deps, dev extras, ruff (line-length 120) and mypy config. |
| `README.md` | docs | Purpose, install, usage quickstart, pointer to `examples/cfb.py`. |
| `CHANGELOG.md` | docs | Release history. |
