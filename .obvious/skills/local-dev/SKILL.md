---
name: local-dev
description: Stand up and verify a local dev environment for keeks-elote (uv + Makefile; pure Python library, no services)
---

# Local dev onboarding — keeks-elote

Durable record of the 2026-09-06 onboarding run. This repo is a **pure Python library**:
no server, no ports, no Docker/Compose, no database, no env vars. "Local dev" = venv +
editable install + green checks + a working library exercise.

## Steps (verified working)

1. **uv** — not preinstalled on the sandbox. `pip install uv` (got uv 0.12.10). No curl
   installer needed.
2. **Install** — `make install`. Creates `.venv/` with system `python3` (3.13.14) via
   `uv venv`, then `uv pip install --python .venv/bin/python -e '.[dev]'`. Pulls
   keeks, elote, pytest(+cov,mock), mypy, ruff and their transitive deps (pandas, scipy
   come in via keeks/elote).
3. **Tests** — `make test` → 71 passed, 97% coverage (`keeks_elote`), ~4s.
4. **Typecheck** — `make typecheck` → mypy: no issues in 5 source files.
5. **Lint** — `make lint` → ruff check clean, `ruff format --check`: 17 files formatted.
6. **Primary flow (library API)** — run the README quickstart: build a `Dict[int, List[dict]]`
   of games with `winner`/`loser` (+ American `winner_odds`/`loser_odds`), a
   `LambdaArena(lambda a, b: True, base_competitor=GlickoCompetitor)`, a keeks
   `BankRoll(initial_funds=10000, percent_bettable=0.5, max_draw_down=1.0)` and
   `KellyCriterion(payoff=1.0, loss=1.0, transaction_cost=0.0)`, then
   `Backtest(arena).run_explicit(data, strategy, bankroll, period_to_start_betting=1)`.
   Verified: 4 periods, 2 settled bets, bankroll 10000 -> 8642.86, `bet_history` populated.
7. **Full example** — `cd examples && ../.venv/bin/python cfb.py`. Verified: 19 weekly
   periods of 2017 CFB data, final bankroll 2917.60, clean exit.

## Gotchas

- `examples/cfb.py` opens `./data/*.json` **relative to CWD** — run it from `examples/`,
  not the repo root.
- `.gitignore` does not list `.venv/`; the Makefile creates it in the repo root. On the
  onboarding sandbox it is covered by a local exclude — never stage `.venv/`.
- `uv.lock` is gitignored on purpose; CI's `floor` job pins floors via
  `--resolution lowest-direct` instead.
- `pytest` config lives in `pyproject.toml` (`configfile: pyproject.toml`); ruff
  line-length is 120 and `E501` is ignored.

## Fast health check (re-verify any time)

    make lint && make typecheck && make test
    cd examples && ../.venv/bin/python cfb.py
