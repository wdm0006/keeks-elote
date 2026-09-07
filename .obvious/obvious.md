# keeks-elote — Agent Guide

**Repo:** [wdm0006/keeks-elote](https://github.com/wdm0006/keeks-elote) (default branch: `master`)
**What it is:** A Python library that couples the [`elote`](https://elote.mcginniscommawill.com)
rating-system library with the [`keeks`](https://keeks.mcginniscommawill.com) bankroll-management
library, so rating-driven predictions can be backtested against betting strategies.

## Stack

| Aspect | Value |
|---|---|
| Language | Python >= 3.10 (classifiers 3.10–3.13; CI matrix tests 3.10–3.14) |
| Project type | Pure library (`keeks_elote` package) — **no server, no ports, no external services** (no DB / Redis / Docker) |
| Package manager | `uv` (Makefile and CI both drive `uv venv` + `uv pip install`) |
| Build backend | hatchling |
| Runtime deps | `keeks>=0.3.0`, `elote>=1.2.0` |
| Dev tools | pytest + pytest-cov + pytest-mock, mypy, ruff |
| Env vars required | none |

## Commands

All development flows through the `Makefile` (it creates and uses `.venv/` via uv):

| Task | Command |
|---|---|
| Create venv + install editable with dev extras | `make install` |
| Run tests with coverage | `make test` |
| Type-check | `make typecheck` |
| Lint + check formatting | `make lint` (alias: `make check`) |
| Auto-fix lint + reformat | `make format` |
| Delete `.venv/` | `make clean` |
| Full worked example | `cd examples && ../.venv/bin/python cfb.py` |

Raw uv equivalents (what the Makefile runs): `uv venv .venv --python python3`,
`uv pip install --python .venv/bin/python -e '.[dev]'`,
`uv run --python .venv/bin/python pytest --cov=keeks_elote tests/`,
`uv run --python .venv/bin/python mypy keeks_elote/`,
`uv run --python .venv/bin/python ruff check . && uv run --python .venv/bin/python ruff format --check .`

## Codebase map

See [codebase-map.md](codebase-map.md) for the folder-level table. In one line:
`keeks_elote/` (the library; core logic in `backtest.py`, the `create_arena` factory in `arena_factory.py`), `tests/` (124 pytest tests, the package root's surface pinned by `test_public_api.py`),
`examples/` (CFB worked example + JSON data), `.github/workflows/` (CI matrix + PyPI publish).

## Local verification

Verify a change with `make lint && make typecheck && make test` — all three must be green.
The primary user flow (library has no server) is exercising the public API, i.e. the README
quickstart (`Backtest.run_explicit` over a small period-keyed dataset) and `examples/cfb.py`.

### Local Verification Summary (onboarding run, 2026-09-06, Python 3.13.14 / uv 0.12.10)

- `make install` — ok; `.venv` created, editable install with `.[dev]` extras.
- `make test` — **71 passed**, coverage **97%** (`keeks_elote`: 235 stmts, 8 missed).
- `make typecheck` — mypy: `Success: no issues found in 5 source files`.
- `make lint` — ruff check: `All checks passed!`; ruff format --check: `17 files already formatted`.
- README quickstart (`Backtest.run_explicit`, `period_to_start_betting=1`) — ran 4 periods,
  settled 2 bets, `bet_history` records stakes/profits/bankroll consistently; final
  `total_funds` 8642.86 from 10000.00 start.
- `examples/cfb.py` — full 19-period 2017 CFB season backtest (Glicko ratings + Kelly
  criterion), completed cleanly; final bankroll 2917.60.

## Sandbox snapshot

- **snapshotId:** `isxn6nefa7z8g1jndqjg9`
- **builtAt:** 2026-09-06T20:18:06.145Z
- **State:** fresh `master` checkout + `.venv/` with `.[dev]` installed via uv; dev stack
  verified healthy (tests / typecheck / lint / example all green) before capture.

## Notes for agents

- `uv` is not always preinstalled; `pip install uv` is enough (no network script needed).
- `examples/cfb.py` uses relative `./data/...` paths — run it **from the `examples/` directory**.
- `.gitignore` does not list `.venv/` (the Makefile creates it in the repo root); on this
  sandbox it is excluded via local ignore. Avoid ever staging `.venv/`.
- `uv.lock` is gitignored; dependency floors are exercised by the `floor` job in CI
  (`uv pip install --resolution lowest-direct -e .`).
