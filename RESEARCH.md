# Research Log

Running record of experiments, rejected candidates, and findings.
Use this before re-testing an idea — it may already have been tried.

---

## ETF candidates

### SPXL and TQQQ — rejected 2026-07-01

**What:** Tested adding SPXL (3x S&P500) and TQQQ (3x QQQ) at 5% each, reducing SPMO from 80% to 70%.

**Optimization result:** `python -m tools.optimize SPXL TQQQ` — no param combination passed constraints across any OOS fold (2022–2025). Every combo hit >-50% drawdown or margin calls.

**Why it fails:** Both are already 3x leveraged internally. The strategy adds 2x margin on top when bullish, creating ~6x effective exposure to S&P500/QQQ. Any significant correction produces catastrophic drawdowns before the MA signal flips bearish.

**Portfolio impact (MA50/100, unvalidated):**
| | Old (SPMO 80% + GLD 20%) | New (+SPXL/TQQQ 5% each) |
|---|---|---|
| CAGR | 36.5% | 35.3% |
| Sharpe | 1.14 | 1.00 |
| MaxDD | -33.4% | -44.4% |

Aggregate got worse on every metric. TQQQ strategy CAGR (25.2%) was even below its B&H (35.9%) — the 100-day slow MA is too slow to protect against 3x intraday swings.

**Conclusion:** Internal-leverage ETFs (2x, 3x) are incompatible with this strategy's 2x margin overlay. Stick to single-leverage ETFs and let the strategy provide the leverage.

---

### ETF screener results — 2026-07-01

Common period 2020-01-02 – 2026-07-01, MA50/100 for all (unoptimized).

| Ticker | B&H CAGR | Strat CAGR | Alpha | Sharpe | MaxDD | Corr to SPMO |
|--------|----------|------------|-------|--------|-------|--------------|
| SPMO   | 23.6%    | 38.0%      | +14.3% | 1.07  | -37.7% | 1.00 |
| GLD    | 15.8%    | 27.7%      | +11.9% | 0.92  | -38.9% | 0.16 |
| QQQ    | 21.3%    | 32.8%      | +11.5% | 0.93  | -50.8% | 0.88 |
| VGT    | 23.6%    | 32.7%      | +9.1%  | 0.87  | -53.6% | 0.88 |
| IWM    | 11.0%    | 17.4%      | +6.4%  | 0.60  | -50.0% | 0.75 |
| EEM    | 8.2%     | 14.2%      | +6.0%  | 0.56  | -52.6% | 0.71 |
| EWJ    | 9.4%     | 12.0%      | +2.6%  | 0.52  | -44.0% | 0.67 |
| TLT    | -4.2%    | -9.7%      | -5.4%  | -0.35 | -63.2% | -0.12 |

### QQQ — validated but not added, 2026-07-01

**Optimize result:** MA10/100, 4/4 OOS folds, avg CAGR 24.4%, avg vs B&H +6.3%.

Strong alpha and fully OOS-validated. Not added because correlation to SPMO is 0.88 — it moves in lockstep. Adding QQQ concentrates the equity bet further without diversification benefit. If SPMO turns bearish, QQQ will too.

**Conclusion:** Good ETF on its own, but redundant alongside SPMO. Revisit only if replacing SPMO.

### IWM — screener alpha didn't survive OOS validation, 2026-07-01

**Screener:** +6.4% in-sample alpha looked promising.

**Optimize result:** MA50/100, 4/4 OOS folds — but avg CAGR only 5.0%, avg vs B&H **-0.2%**. Strategy barely keeps pace with IWM buy-and-hold after fees.

**Lesson:** Screener alpha is in-sample (full period). Always run `optimize` before adding — the OOS folds are the real test. IWM's alpha was curve-fitted to the full history, not robust.

**Conclusion:** Rejected. Near-zero OOS alpha doesn't justify the added complexity.

### TLT — rejected at screener, 2026-07-01

Negative alpha (-5.4%), negative Sharpe (-0.35). MA crossover destroys value on bonds — they don't trend the same way equities do. Optimization not needed.

**Conclusion:** Bonds are incompatible with this strategy. Use GLD for the defensive allocation.

### EWJ / EEM — rejected at screener, 2026-07-01

Low alpha (+2.6% / +6.0%), low Sharpe (0.52 / 0.56), MaxDD near the -50% constraint. Macro/sector-rotation ETFs don't trend well on MA crossover signals. Optimization not run.

**Conclusion:** Confirmed the Roadmap note — near-zero alpha. Would need a mean-reversion strategy, not momentum.

### VGT — rejected at screener, 2026-07-01

+9.1% alpha but 0.98 correlation to QQQ and 0.88 to SPMO. Essentially the same bet as QQQ and SPMO. No diversification value.

**Conclusion:** Not worth testing further while SPMO is in the portfolio.

---

## Portfolio construction

### Dynamic GLD allocation — tested, not adopted, 2026-07-01

**Idea:** When SPMO signal is bearish, shift weight from SPMO into GLD (low correlation: 0.16). Three bear configs tested: 60/40, 40/60, 20/80 SPMO/GLD.

**Full-period result (2020–2026):**
| Config | CAGR | Sharpe | MaxDD | vs static |
|--------|------|--------|-------|-----------|
| Static 80/20 | 37.9% | 1.20 | -30.4% | — |
| Dynamic bear 60/40 | 39.3% | 1.24 | -30.3% | +1.4% |
| Dynamic bear 40/60 | 40.3% | 1.25 | -30.3% | +2.5% |
| Dynamic bear 20/80 | 41.0% | 1.22 | -30.3% | +3.1% |

**OOS validation (2022–2026 folds):**
| Fold | Static | Dyn 40/60 |
|------|--------|-----------|
| 2022 | -9.8% | -6.9% ✓ |
| 2023 | 32.0% | 34.5% ✓ |
| 2024 | 88.6% | 88.6% ✓ |
| 2025 | 34.2% | 33.5% ✗ |
| 2026 | 38.9% | 37.3% ✗ |

Win rate: 3/5 folds (60%) across all configs.

**Why the OOS is weak:** The full-period gains concentrate in 2020 (COVID, GLD spiked) and 2022. In 2025–2026 GLD underperformed during SPMO bear periods, so the shift hurt. The improvement is GLD-macro-environment-dependent, not structurally consistent.

**Conclusion:** Not adopted. Fixed 80/20 allocation is simpler and the OOS evidence doesn't justify the operational overhead of rebalancing on signal flips. Revisit if GLD's role in the portfolio changes or a third uncorrelated asset with clearer bear-regime alpha is found.

**Tools added:** `python -m tools.portfolio --dynamic` (full-period comparison), `python -m tools.portfolio --dynamic --oos` (fold-by-fold validation).

---

## Signal configs

### MA+RSI+MACD vs MA-only — rejected (pre-2026)

Multi-signal combos were tested for SPMO. Result: 5x more trades, no net improvement in OOS CAGR after fees. MA-only is simpler and survives costs better.

**Conclusion:** Default to MA-only. Only revisit multi-signal if a ticker shows clear single-signal weakness across multiple OOS folds.
