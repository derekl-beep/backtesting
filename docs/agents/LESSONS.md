# Lessons Log

Record of mistakes and their corrections. Append-only between consolidations (a
consolidation — triggered per MAINTENANCE.md — may promote entries to rules and move
superseded ones to `docs/archive/`). Format and consolidation rules:
[MAINTENANCE.md](MAINTENANCE.md). Read this before starting non-trivial work — these are
the failure modes this repo has actually produced.

Seeded 2026-07-07 from documented history (sources: `research/`, `docs/WORKFLOW.md`).

## 2026-07-06 — RSI inverted on zero-loss windows

- **What happened:** `signals/rsi.py` computed RSI=0 (max oversold) for a 14-day window
  with zero losses; correct is RSI=100 (max overbought). Shipped for months; found only
  while building the mean-reversion tool.
- **Wrong belief:** `gain / loss.replace(0, inf)` handles the zero-loss edge — it silently
  computes the exact opposite.
- **Correction:** let the division produce inf naturally; flat window (zero gain AND loss)
  = neutral 50. Regression tests in `tests/test_rsi.py`.
- **Rule change:** edge cases of money-math need pinned tests at the time they're written,
  not later (JUDGMENT.md §5 execution/test gates).

## 2026-07-03 — Monthly equity curve fed to a daily annualizer

- **What happened:** first sector-rotation backtest reported CAGR 900–2300%, Sharpe 3–4.6.
  `core/metrics.calc()` assumes daily frequency (252/yr); it got a ~120-point monthly series.
- **Wrong belief:** metrics.calc works on any equity series.
- **Correction:** reindex non-daily curves to daily (ffill) before calling calc.
- **Rule change:** plausibility table (JUDGMENT.md §6) — out-of-range numbers are bugs
  until proven otherwise.

## 2026-07-06 — Significance-test null lacked the strategy's leverage

- **What happened:** leveraged sector rotation vs an *unleveraged* random null returned
  p=0.000 "significant." The apparent skill was just the leverage the null didn't have.
- **Wrong belief:** the null only needs the same tickers/calendar, not the same mechanism.
- **Correction:** the null must get identical machinery (leverage, fees, calendar). Locked
  by `test_significance_test_null_applies_the_same_leverage_as_actual`.
- **Rule change:** JUDGMENT.md §7.3.

## 2026-07-03 — Optimizer silently dropped constraint-failing folds

- **What happened:** `tools.optimize SMH` output just ended at 2022 with no message —
  every 2023+ fold was skipped because no combo passed the -50% MaxDD constraint. Looked
  like "not enough data."
- **Wrong belief:** absence of output rows = absence of data.
- **Correction:** explicit `SKIPPED — no combo passed constraints` line added.
- **Rule change:** silent omission is a bug class; tools must say why something is missing
  (JUDGMENT.md §6 checklist item 4).

## 2026-07-01 — Per-fold OOS averages hid a compounding loss

- **What happened:** optimizer recommended MA10/100 for SPMO (best per-fold avg alpha);
  full-period CAGR was 8.7% *lower* than MA10/200 because each fold resets equity —
  fold-averaging smoothed over a missed 2021 compounding gap. (Initial fee-based
  explanation was also wrong; corrected 2026-07-03 in `research/signal_configs.md`.)
- **Wrong belief:** best average-per-fold = best full-period.
- **Correction:** validate retunes at portfolio level over the full period (`tools.tune`),
  not per-ticker fold averages alone.
- **Rule change:** CLAUDE.md routes retuning through `tools.tune`.

## 2026-07-05 — Docs drifted from code (three copies, one updated)

- **What happened:** memory + README + CLAUDE.md all carried architecture/param copies;
  code moved (`SIGNAL_CONFIGS` → `core/portfolio_config.py`) and only some copies followed.
  WORKFLOW.md's bug findings never propagated anywhere.
- **Wrong belief:** writing a fact in more places makes it more available. It makes it
  wrong in more places.
- **Correction:** single-owner-per-fact table (DIAGNOSIS.md), everything else links.
- **Rule change:** the 2026-07-07 doc system itself.
