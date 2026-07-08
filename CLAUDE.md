# SPMO + GLD Portfolio — Agent Guide

Momentum margin-strategy backtester for a two-ETF portfolio (SPMO 80% + GLD 20%).
**Real money follows this repo's outputs.** Derek uses `tools.signal` for daily margin
decisions on Futu HK. A confidently wrong number is worse than a crash.

This file is a router. Read the linked doc when a session actually needs it — do not
preload everything.

## Run environment

```bash
.venv/bin/python -m tools.<name> [args]   # no venv activation, no plain `python`
.venv/bin/pytest                          # test suite
```

## Live portfolio (orientation only — code is the truth)

`PORTFOLIO` in `core/portfolio_config.py` is the **single source of truth** for weights and
signal params (currently SPMO 80% MA10/200, GLD 20% MA20/100). Backtests, live checks, and
`tools.tune --apply` all read/write it. Never edit numbers about the live portfolio
anywhere else.

## Where to look

| Need | Read |
|---|---|
| Run any tool / command flags / architecture | `docs/TOOLS.md` |
| Before testing ANY strategy or ticker idea | `research/README.md` (it may already be tested); `research/methodology.md` first |
| Open research questions | `research/open_questions.md` |
| How to delegate to subagents, model choice, validation | `docs/agents/ORCHESTRATION.md` |
| Decision rubrics: done? escalate? ask Derek? wrong direction? | `docs/agents/JUDGMENT.md` |
| Ready-made delegation prompts | `docs/agents/TEMPLATES.md` |
| Editing these docs / recording lessons | `docs/agents/MAINTENANCE.md` |
| Past mistakes to not repeat | `docs/agents/LESSONS.md` |
| Why this system exists, known weak points | `docs/agents/DIAGNOSIS.md`, `docs/agents/LETTER.md` |

## Iron rules (checkable, no judgment required)

1. **Test gate:** after any edit under `core/`, `signals/`, `strategies/`, `tools/`, or
   `tests/`, run `.venv/bin/pytest` before reporting done. A failing golden test
   means strategy behavior changed — report it to Derek; never update pinned values to make
   it pass (exception process: `docs/agents/JUDGMENT.md` §5).
2. **Holdout:** never run `tools.optimize --final` unless Derek explicitly asks — it
   consumes the once-per-year held-out test.
3. **Real-money changes need Derek's explicit yes:** editing `core/portfolio_config.py` or
   `core/config.py`, adding/removing a portfolio leg, shipping a new overlay, or relaxing
   the -50% MaxDD constraint. Backtesting and research are free; deployment is not.
4. **Don't re-test rejected ideas:** check `research/README.md` before starting any
   experiment. Rejected ideas (leveraged ETFs, sector rotation, covered calls, spreads,
   GLD options, continuous-probability signal, most mean-reversion) need materially new
   mechanisms to revisit, not a rerun.
5. **Charts:** `matplotlib.use("Agg")` at the top, save to `charts/<tool>/` with date
   suffix, `plt.close()` after. Never `plt.show()`.
6. **Every backtest number gets a sanity check** against the plausibility table in
   `docs/agents/JUDGMENT.md` §6. Out-of-range = bug until proven otherwise.
7. **Git:** commit only when Derek asks. ETF work on `master`, stock work on
   `feature/stock-backtesting`. No trailing summary prose after finishing work.
8. **A verdict on any experiment requires walk-forward OOS + a significance test**, not a
   full-period in-sample table (the in-sample trap has burned this repo twice — see
   `docs/agents/LESSONS.md`).

## Style (Derek's confirmed preferences)

- Simplest thing that works; no new abstractions/signals beyond the current task.
- Suggest next steps as a short list and wait for his pick — don't start coding them.
- No exit-code echoes after bash commands; no "Done! Here's a summary" closers.

## Session quickstarts

- **Daily check:** `.venv/bin/python -m tools.signal SPMO GLD` — done. No docs needed.
- **New ETF candidate:** workflow in `docs/TOOLS.md` §Common workflows.
- **New strategy experiment:** template in `docs/agents/TEMPLATES.md` §Research.
- **Code change:** iron rules 1, 6, 8 above; delegation guidance in
  `docs/agents/ORCHESTRATION.md`.

## Stock tools

Live on the `feature/stock-backtesting` branch, not `master`. Catalog in `docs/TOOLS.md`
§Stock tools.
