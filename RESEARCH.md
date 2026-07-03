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

### Extended history + alpha filter — params unchanged, 2026-07-01

Extended backtest history from 2020 to 2016 (SPMO launch), giving 8 OOS folds (2018–2025) vs 4 previously. Also fixed a tie-breaking bug in the optimizer (was picking by insertion order; now breaks ties by avg vs B&H). Added `MIN_AVG_ALPHA = 5%` filter to exclude params that pass constraints but don't meaningfully beat B&H.

**New optimizer recommendations:**
- SPMO: MA10/100 (7/8 folds, avg +10.4% vs B&H) — previously MA50/100
- GLD: MA20/100 (8/8 folds, avg +7.3% vs B&H) — previously MA30/50

**Portfolio test result (MA10/100 / MA20/100):**
| | Old params | New params |
|---|---|---|
| CAGR | 36.5% | 27.8% |
| Sharpe | 1.14 | 1.00 |
| Fees | ~$102 | $254 |

**Why new params underperformed:** ~~MA10 fast window whipsaws 2.5x more, generating extra trades and fees that eat the per-fold OOS alpha.~~ **Correction (2026-07-03):** fees are not the cause — at $10K capital, MA10/100 paid $254 total vs $108 for MA10/200 over 10 years, a difference that rounds to 0.0% CAGR impact. The real reason is the slow MA choice. MA10/200 keeps you in bull regimes longer before flipping bearish; in 2021 alone this was worth +14.9% (MA10/200: 42.9% vs MA10/100: 28.0%). That single-year gap compounds into a lower ending equity that the OOS fold averages smooth over (each fold resets to its own equity, so per-fold alpha looks higher for MA10/100 even though full-period CAGR is lower).

**Why the heatmap shows MA10/100 ahead:** The sensitivity heatmap reports avg OOS alpha per fold — MA10/100 catches more regime entries across folds and shows +9.2% avg alpha vs +1.5% for MA10/200. But full-period CAGR is dominated by compounding: missing 15% in a strong year like 2021 permanently reduces the base for all future returns. The fold-level average doesn't capture this.

**Conclusion:** Keeping MA10/200. The longer slow window wins on full-period compounding by staying in strong bull runs longer. Fee drag is negligible at current capital sizes. The `MIN_AVG_ALPHA` filter and tie-breaking fix remain in the optimizer for future use.

### MA+RSI+MACD vs MA-only — rejected (pre-2026)

Multi-signal combos were tested for SPMO. Result: 5x more trades, no net improvement in OOS CAGR after fees. MA-only is simpler and survives costs better.

**Conclusion:** Default to MA-only. Only revisit multi-signal if a ticker shows clear single-signal weakness across multiple OOS folds.

### Sensitivity heatmap baseline — 2026-07-01

First run of `python -m tools.sensitivity` (new tool: full MA grid evaluated directly
on all 8 OOS folds, per ticker).

**SPMO (current MA10/200):** on a plateau — every grid cell passes 8/8 folds with
positive alpha — but in the weakest column (+1.5% avg OOS alpha vs +9–10% for the
MA*/100 column). This is the per-ticker view of the known joint-optimizer tradeoff:
MA10/200 trades per-ticker alpha for fewer trades/fees and better portfolio Sharpe
(see "Extended history + alpha filter" entry). Not a red flag, but if the portfolio
context changes (e.g. GLD removed), revisit the /100 column.

**GLD (current MA20/100):** mid-plateau, +7.3% avg OOS alpha, all 8 neighbors
positive (+3.1% to +11.7%). Robust.

**Rolling 1y Sharpe gap (strategy − B&H):** SPMO full-history −0.17, last year −0.37;
GLD −0.17 / −0.08. Negative full-history gaps are expected (the strategy wins on
drawdown/total-return compounding, not per-period Sharpe); watch for the SPMO gap
widening further.

---

## Call options overlay — initial research, 2026-07-03

### Concept

Add long QQQ calls as a convexity kicker on top of the existing 2x margin strategy.
Signal source stays SPMO MA10/200. Buy calls at each bull regime start, close at bear flip.
This is an overlay — the margin leg runs unchanged underneath.

**Why QQQ, not SPMO:**
- SPMO options: 5 expiries only (max ~6.5 months), ATM spreads 17–24%, OI <1000 — too illiquid for systematic use
- QQQ: 28 expiries including LEAPS, ATM spreads <1%, deep OI
- Signal transfer: SPMO signal applied to QQQ gives **88% win rate** vs 62% on SPMO itself. SPMO's duds are factor-rotation events (momentum vs value); the broader market (QQQ) is unaffected.

**Why ATM (Δ0.50), not OTM or deep ITM:**
- Deep ITM (Δ0.85): cheaper leverage but costs $4–8K premium/regime (mostly intrinsic), wins 8/9 but median RoP only +104%
- ATM (Δ0.50): wins **9/9**, median RoP +210%, costs ~$2–3K/regime (before dynamic sizing). IV-shocked (+20%) still 8/9, median +158% — robust
- OTM (Δ0.30): highest headline RoP (+290%) but falls to 6/9 with IV shock and -45% worst regime — too fragile

### Regime statistics (SPMO, 9 regimes since 2016)

| Metric | Value |
|--------|-------|
| Median duration | 221 days |
| Median QQQ return over regime | +14–18% |
| Signal transfer win rate (QQQ) | 88% (8/9 closed regimes positive) |
| Best regime (QQQ) | +54% (2020–2022) |
| Worst closed regime | −3.6% (Feb 2022, 7 days — whipsaw) |
| ATM call during 7-day whipsaw | +12% RoP (still had 5 months of life left) |

### Budget sweep — dynamic sizing (3% of current equity per regime)

The critical insight: **budget must be sized to current portfolio equity, not fixed initial capital.** With fixed $100K sizing, by 2025 the portfolio is $685K but options are still bought at $3K (0.4% of actual capital). Dynamic sizing fixes this and lets option gains compound.

**Margin-only baseline: CAGR 28.0%, Sharpe 0.97, MaxDD −35.8%**

| Budget | CAGR | Sharpe | MaxDD | CAGR lift |
|--------|------|--------|-------|-----------|
| 1% | 28.5% | 1.01 | −32.4% | +0.5% |
| 3% | 29.9% | 1.06 | −27.5% | +1.9% |
| 5% | 31.6% | **1.06** | −22.6% | +3.6% |
| 7% | 33.4% | 1.00 | −22.9% | +5.4% |
| 10% | 36.2% | 0.91 | −23.2% | +8.3% |
| 15% | 42.0% | 0.78 | −23.9% | +14.0% |
| 20% | 48.3% | 0.72 | −26.5% | +20.4% |

**Sharpe sweet spot: 3–5% budget.** Both improve Sharpe above baseline (1.06 vs 0.97) while meaningfully lifting CAGR. MaxDD also shrinks because call gains cushion regime peaks.

**Past 7%:** CAGR keeps rising but Sharpe dips below baseline — option premium draws introduce equity-curve volatility. MaxDD actually ticks back up past 15% (lumpy cash flows at large scale).

**Practical sizing for 10% budget at scale:** by 2026 the portfolio is ~$1M, so 10% = $100K in premium per regime. Real money at risk per entry. Start at 3–5% and scale up as conviction grows.

### IV sensitivity

Rerun with +20% implied vol at entry (i.e., you buy when options are expensive):
- ATM Δ0.50: win rate drops from 9/9 → 8/9, median RoP drops +210% → +158%. Still comfortably positive.
- OTM Δ0.30: drops to 6/9, worst regime −45%. Fragile.
- Conclusion: ATM is robust to expensive entry vol; OTM is not.

### Tool

`python -m tools.options_backtest`                   — per-regime breakdown, all three deltas
`python -m tools.options_backtest --combined`        — margin + overlay equity curve (ATM, 3%)
`python -m tools.options_backtest --sweep`           — budget sweep table + chart (ATM default)
`python -m tools.options_backtest --delta 0.30 --sweep`  — OTM version

### Rolling model — key findings, 2026-07-03

Implemented rolling: close at 30 DTE, open a new ATM call. Each regime can span multiple legs (max 150 calendar days per leg = 180-day tenor minus 30-day roll buffer).

**Long regimes have multiple legs:**
| Regime | Duration | Legs | QQQ return | RoP |
|--------|----------|------|------------|-----|
| 2016–2018 | 738 days | 5 | +49.0% | +70% |
| 2020–2022 | 622 days | 5 | +54.1% | +38% |
| 2023–2025 | 659 days | 5 | +15.6% | +26% |

**Last leg of every long regime is a loser.** The regime ends because SPMO is weakening, which means QQQ is also weakening — so the final call leg is entered when the underlying starts to fade. All three 5-leg regimes had a negative or near-zero final leg. This is structural, not bad luck: the exit signal lags price by design (200-day MA). Accept the last-leg loss as the cost of not exiting early and giving up mid-regime gains.

**Short regimes (< 150 days) are single-leg and usually small wins.** The 7-day whipsaw (Feb 2022) returned +12% RoP because the call still had 5 months of life left when it closed — time value wasn't meaningfully damaged.

**Rolling vs non-rolling:** prior single-leg model overstated returns on long regimes by only entering once per regime. The rolling model is correct: it actually trades each leg and compounds properly. Backtest results should only be cited from the rolling model (`run()` now always uses rolling).

**Strategy comparison (3% overlay budget on combined):**
| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Margin only | 28.0% | 0.97 | −35.8% |
| Options-only (10%) | 22.9% | 1.47 | 0.0% |
| Combined (3%) | 34.6% | 0.99 | −27.3% |
| QQQ B&H | 20.5% | 0.95 | −35.1% |

Sweet spot: **combined at 3–5% overlay.** Lifts CAGR +6–8% over margin-only while keeping Sharpe flat and reducing MaxDD by ~8%. Options-only is interesting as a capital-efficient sidecar (zero drawdown) but lower CAGR than combined.

### Open questions for next session

1. **Exit rules:** currently hold to bear flip. Test: (a) profit target on option (+100% RoP → scale out), (b) time-roll at 60 DTE remaining, (c) roll-up on strength. The 2016–2018 regime peaked mid-way — a trailing stop could capture more.
2. **Entry filter:** enter on regime flip always, or wait N days / filter by VIX level? High-VIX entries had the best returns (2020, 2025) — filtering them out would be wrong.
3. **GLD leg:** GLD has decent options liquidity. Could run a parallel GLD call overlay on GLD's own signal (MA20/100). Not yet tested.
4. **Real execution:** Futu HK options access, contract costs, margin treatment of long calls. Need to verify before committing capital.
