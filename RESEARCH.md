# Research Log

Running record of experiments, rejected candidates, and findings.
Use this before re-testing an idea — it may already have been tried.

---

## ETF candidates

### SMH (semiconductors) — strong momentum alpha, blocked by drawdown constraint, 2026-07-03

**What:** Screened SMH/SOXX (semiconductor sector ETFs) alongside factor ETFs (MTUM, QUAL,
USMV) and sector ETFs (XLK, XLE, XLF, XLV) as untested momentum candidates.

**Screener result (MA50/100 baseline, 2016–2026):** SMH showed the largest alpha of any
ETF tested to date — B&H CAGR 35.8%, strategy CAGR 58.2%, **alpha +22.3%, Sharpe 1.10**
(exceeds SPMO's own 0.94). SOXX nearly identical (+19.3% alpha, 0.99 correlation to SMH —
redundant, pick one). Correlation to SPMO: **0.76** — meaningfully lower than QQQ (0.88) or
MTUM (0.91), i.e. real diversification potential if it clears validation.

**Optimize result:** `tools.optimize SMH` only produces per-fold data through 2022 — 2023,
2024, 2025 silently disappear from the table with no error. Root cause (confirmed by
reproducing `_run_params` directly): the optimizer's training window is *expanding*
(2016 → test_year−1), and SMH's training set crosses a real -60% drawdown once the 2022
chip-sector crash enters it. Because `max_dd` is measured over the whole growing window,
every fold from 2023 onward inherits a training-set max_dd beyond `MAX_DRAWDOWN_LIMIT`
(-50%), so *zero* of the 15 MA combos ever pass the constraint again — for any future year,
permanently. This isn't a math bug (the -50% hard limit is doing exactly what it's supposed
to), but the tool gives no indication why folds vanish; see the tool-improvement note below.

**Does a filter fix the drawdown?** `tools.compare SMH` — tried MA+RSI, MA+MACD, MA+cash
(0x on bearish), MA+SH hedge. None bring MaxDD under -50% (range: -58.8% to -66.4%, vs
SMH's own unleveraged B&H MaxDD of -45.3%). The 2x margin overlay itself is what pushes the
2022 crash past the limit, not a lag in the exit signal — even instant-cash-on-bearish still
breaches it.

**Follow-up: does it work unleveraged? No — rejected, 2026-07-03.** Tested SMH at 1x directly
(`strategies.momentum.positions(sig, leverage=1.0, no_signal_leverage=0.0)` — full exposure
when bullish, cash when bearish, no margin at all). Result: CAGR 25.8%–31.3% across the same
MA candidates, all **below SMH's own B&H CAGR of 35.8%** — negative alpha (-4.5% to -11.9%
full-period). Walk-forward OOS confirms it's not a fluke: every candidate shows **negative
avg OOS alpha (-12.4% to -22.8%) across all 8 folds**, worse than simply holding SMH. The 2x
margin overlay isn't just adding risk on top of a working 1x signal — the 1x signal alone
loses to buy-and-hold. All of SMH's apparent edge lives specifically in the 2x-leverage-
during-confirmed-uptrend mechanism (see Methodology note below), which is exactly the
mechanism blocked by the drawdown constraint. There is no viable unleveraged path for SMH.

**Conclusion:** Rejected. SMH has genuinely strong 2x-leveraged backtest numbers, but (a) the
2x version breaches the drawdown constraint from 2022 onward and (b) the unleveraged version
underperforms simple buy-and-hold. Revisit only if the -50% drawdown limit is deliberately
relaxed for a small satellite allocation, understanding that means accepting a real ~-60%
peak-to-trough event (2022 was not a backtest artifact — it happened).

### Methodology: reported "alpha" is a leverage-timing effect, not signal quality — 2026-07-03

**Why this matters:** every alpha number in this log and in `tools.screen`/`tools.optimize`
output compares a **2x-leveraged** strategy CAGR against a **1x** buy-and-hold CAGR. That
comparison conflates two different things: (1) does the MA signal correctly identify
good/bad periods, and (2) does adding 2x leverage during identified good periods lift
returns. Isolating (1) by testing the *same* signal at 1x (no margin) reveals which one is
actually doing the work.

**Direct test on the deployed legs:**
| Ticker (params)  | B&H CAGR | 1x, cash-timed CAGR | vs B&H | 2x margin CAGR | "Alpha" reported |
|---|---|---|---|---|---|
| SPMO (MA10/200)  | 19.8% | 16.0% | **-3.7%** | 29.3% | +9.6% |
| GLD (MA20/100)   | 13.2% | 13.7% | **+0.5%** | 20.4% | +7.3% |

At 1x, the signal alone is roughly flat-to-negative vs simply holding the ticker — SPMO's
own market-timing is *worse* than buy-and-hold once leverage is removed. (A third variant,
1x-bull/1x-hold-bear, is mathematically identical to B&H by construction — the position
never changes, so it isn't a useful comparison point, just a sanity check that the math is
consistent.)

**What this means for every other finding in this log:** the strategy's real edge is
"add 2x leverage during confirmed uptrends, never go below 1x" — a structurally low-risk way
to harvest extra return from a persistent trend, not a claim that the MA crossover has
genuine predictive skill at picking good days to be in the market. The `-50%` drawdown
constraint is really a proxy for "how much 2x-leverage-alpha can this ticker's volatility
profile support" — which is exactly why SMH/TQQQ/UPRO/SOXL get excluded (too volatile to
safely carry 2x) while SPMO/GLD survive (moderate enough volatility that 2x rarely breaches
-50%). Any future candidate screening should read "Strategy CAGR vs B&H" as "how much
leverage-timing alpha is extractable here without breaching risk limits," not as "is this a
good stock-picking signal."

**Tool gap found:** `tools/optimize.py::_run_params` silently swallows exceptions and
`_sweep_folds` silently drops any fold where zero combos pass constraints — a ticker with
one bad historical crash goes quietly "unoptimizable" from that point forward with no
message, easy to mistake for "not enough data." Should print an explicit
`"N/8 folds: no combo passed max_dd constraint"` line instead of just omitting rows.

### MTUM and XLK — validated alpha, too correlated to add, 2026-07-03

**MTUM** (iShares MSCI USA Momentum Factor ETF — a live momentum-factor fund, direct
comparison point for this strategy): `tools.optimize MTUM` → MA30/50, 3/8 folds, avg CAGR
31.7%, avg vs B&H **+13.3%**. Real OOS-validated alpha.

**XLK** (Technology Select Sector SPDR): `tools.optimize XLK` → MA10/100, 5/8 folds, avg
CAGR 35.8%, avg vs B&H **+16.5%**. Also real OOS-validated alpha.

**Why not added:** Correlation to SPMO is 0.91 (MTUM) and 0.85 (XLK) — both move in
lockstep with the existing SPMO leg. Same conclusion as the existing QQQ entry below:
genuine alpha, but adding either would concentrate the equity-momentum bet further rather
than diversify it.

**Conclusion:** Rejected for the current portfolio for the same reason as QQQ. Revisit only
if SPMO is being replaced rather than supplemented.

### QUAL, USMV, XLE, XLF, XLV — rejected at screener, 2026-07-03

Screened alongside MTUM/XLK. All showed flat-to-negative alpha at MA50/100 baseline
(QUAL +2.2%, USMV -0.0%, XLE -5.1%, XLF -0.9%, XLV -6.8%) with Sharpe ≤0.66. Consistent
with the existing EWJ/EEM/TLT/VGT findings: defensive-factor (USMV), value/cyclical-sector
(XLE, XLF), and non-trending (XLV) exposures don't suit an MA-crossover momentum signal.
Optimization not run — screener alpha this weak has never survived OOS validation for any
prior candidate.

**Conclusion:** Confirmed the established pattern. No further testing needed unless a
different (non-MA-crossover) signal family is introduced — see Roadmap.

### Leveraged ETF rotation (TQQQ / UPRO / SOXL) — tested and rejected, 2026-07-03

Closes Roadmap idea #3 ("Leveraged ETF rotation"), previously flagged but never tested.

**What:** Ran `tools.screen` and `tools.optimize` directly on TQQQ (3x QQQ), UPRO (3x SPY),
and SOXL (3x semiconductors) to see if holding them unleveraged (1x, no margin) when bullish
could substitute for this strategy's 2x margin overlay on single-leverage ETFs, avoiding
margin/borrow cost entirely.

**Screener result (MA50/100 baseline):** all three show strongly *negative* alpha vs their
own buy & hold — TQQQ -21.7%, UPRO -18.3%, SOXL **-40.8%** — despite (or because of) huge
absolute returns (SOXL B&H CAGR 57.4%). Classic leveraged-ETF volatility decay: daily
rebalancing inside the fund erodes returns on choppy/whipsaw price action that a slow MA
crossover can't get in and out of fast enough to avoid.

**Optimize result:** none of the 15 MA combos pass the -50% drawdown constraint for TQQQ or
UPRO even in the very first OOS fold (2018) — MaxDD ranges -53% to -74% in that fold alone.
SOXL fails constraints across its entire history ("No results passed constraints").

**Conclusion:** Rejected. A slow MA-crossover trigger is fundamentally incompatible with
3x-leveraged instruments — the whipsaw cost compounds with the fund's own daily-rebalance
decay. Confirms and extends the existing SPXL/TQQQ finding below (that one tested them as
*additional legs on top of* 2x margin; this one tests them as a full *replacement* for
margin, and the result is the same: leveraged ETFs don't pair with this signal family at
any exposure level). Roadmap item #3 can be closed as tested-and-rejected.

---

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

### Risk-adjusted sizing — findings, 2026-07-03

`python -m tools.sizing` shows Calmar ratio (CAGR / |MaxDD|) and Sharpe across budget fractions 1–20%.

**Calmar is the right metric here.** Sharpe penalizes all volatility equally; retail traders care more about drawdowns (margin calls, psychological limits) than upside vol. Calmar captures exactly the tradeoff we care about.

**Kelly is unreliable with 9 regimes.** Historical win rate of 9/9 (all options regimes profitable) gives Gaussian Kelly of 174% and binary Kelly of infinite — both meaningless for sizing. Kelly requires 30+ loss observations to be reliable. Note for the future: as more regimes accumulate, Kelly will converge to something usable.

**Calmar frontier (at $10K capital, ATM Δ0.50):**
| Budget | CAGR | Sharpe | Calmar | MaxDD | Tier |
|--------|------|--------|--------|-------|------|
| 7%  | 31.8% | 1.10 | 1.14 | −27.8% | Conservative (max Sharpe) |
| 15% | 38.4% | 0.87 | 1.29 | −29.8% | Moderate (max Calmar) |
| 20% | 43.7% | 0.80 | 1.22 | −35.9% | Aggressive (max CAGR) |

- Margin-only baseline: CAGR 27.9%, Calmar 0.78, MaxDD −35.8%
- Every budget level from 1% to 20% improves Calmar above baseline
- Calmar peaks at 15% then declines — high option drawdowns at 20% drag it back down
- Calmar 1.5 target not reached in this data; would require higher sample or larger capital effects

**Practical approach:** start Conservative (7%, max Sharpe), scale toward Moderate (15%) after 3+ live regimes confirm live-trading accuracy of the model.

### New underlyings for the call overlay: GLD rejected, SMH works — 2026-07-03

Tested whether the rolling call-overlay pattern (validated for SPMO signal → QQQ calls)
transfers to other bullish-regime signals: a ticker's own signal driving calls on itself,
rather than the SPMO→QQQ signal-transfer trick. Used `simulate_regime_with_rolls` directly
at ATM (Δ0.50), 3% budget, same rolling/30-DTE-roll methodology as the shipped tool.

**Baseline refresh (SPMO signal → QQQ calls, current data through 2026-07-02):** 9/9 regimes
profitable (100% win rate), median RoP +52%, worst regime still +12% (the Feb 2022 7-day
whipsaw). Confirms the existing finding holds with fresh data — no decay in the edge.

**GLD signal (MA20/100) → GLD calls, IV proxy = `^GVZ` (Cboe Gold ETF Volatility Index, the
correct gold-specific implied-vol series — using `^VIX` here would have been a methodology
error, VIX prices S&P500 options, not gold). **Rejected.** Win rate 4/13 (31%), median RoP
**-55%**, worst -95%. GLD's own MA crossover produces many short regimes (22-173 days,
several under 2 months) relative to the 180-day tenor — each failed regime bleeds most of
the premium to time decay before the underlying makes a real move. The one long 2023–2026
regime (+198% RoP) rescues the average but the median is deeply negative. Unlike SPMO→QQQ,
GLD's signal does not transfer to a long-call structure. Answers open question #3 below.

**SMH signal (MA50/100) → SMH calls, IV proxy = trailing 21-day realized vol (no listed
gold-style vol index for semiconductors, so realized vol is used directly as a conservative
stand-in — likely *understates* true IV, since options typically carry a premium over
realized, so real-world RoP would run somewhat lower than shown here). **Works.** Win rate
7/11 (64%), median RoP **+82%** — actually higher than the SPMO baseline. Stress-tested with
an IV shock (options priced above realized vol, same robustness check used for the SPMO/QQQ
finding): still 6/11 (55%) win rate and +29% median RoP at a conservative +40% shock.

**Why this matters:** SMH was rejected from the margin engine (see ETF candidates section
above) because 2x leverage pushes its 2022 crash past the -50% drawdown constraint — but a
long call's downside is capped at the premium paid, so it can capture SMH's real momentum
edge (established earlier: Sharpe 1.10, the best of any ticker tested) **without** the
unbounded-drawdown problem that blocks margin. This is a legitimate path to adding SMH's
edge to the strategy as a bounded-risk satellite options position, separate from the
margin-based SPMO/GLD legs. Not yet sized or added to any tool — this is exploratory
confirmation that the idea works, not a recommendation to deploy a specific budget yet.

**Caveat (superseded — see real-chain check below):** realized-vol-as-IV-proxy is a bigger
approximation for SMH than `^VIX`-for-QQQ or `^GVZ`-for-GLD (both are actual listed
implied-vol indices; SMH's isn't). Originally assumed this meant real premiums would run
*higher* than modeled — checking a live chain shows the opposite is true right now, see
below.

### New tool: validate the pricing model against a real option chain — 2026-07-03

Built `tools/options_chain_check.py` — pulls the real, live option chain nearest our
modeled tenor/delta for a ticker (via `yfinance`'s `Ticker.options`/`option_chain()`) and
prints it next to what our Black-Scholes model would price, using the same IV proxy the
backtest uses. This is the check flagged as the top toolbox priority: everything in
`options_backtest.py`/`options_signal.py` has been theoretical pricing until now, never
checked against a real quote.

```
python -m tools.options_chain_check QQQ GLD SMH
python -m tools.options_chain_check SMH --delta 0.30
python -m tools.options_chain_check GLD --tenor 90
```

**First live run (2026-07-03, ~180-day ATM calls), and it immediately found real issues:**

| Ticker | Model IV | Real IV | Diff | Model price vs real mid | Real spread | Real OI |
|---|---|---|---|---|---|---|
| QQQ | 15.8% (`^VIX`) | 28.5% | **+12.7pt** | **-38.8%** (model too cheap) | 1.8% (vs 0.3% assumed) | 7,842 |
| GLD | 26.0% (`^GVZ`) | 26.9% | +0.9pt | +18.5% | 12.9% (vs 0.3% assumed) | 30 (thin) |
| SMH | 78.4% (realized vol) | 52.2% | **-26.2pt** | +93.7% (model too expensive) | 7.5% (vs 0.3% assumed) | 85 |

**Findings:**
- **`^GVZ` validates well for GLD** — real IV within 1 point of the proxy. Confirms the
  choice was right, though real GLD LEAPS-style calls (180 DTE) are thin (OI 30, volume 3)
  — a real fill would likely slip from the quoted mid regardless of pricing accuracy.
- **`^VIX` is currently underpricing QQQ's real 6-month IV by ~13 points** — on this
  particular day, QQQ's actual options are pricing in meaningfully more vol than the S&P500
  index VIX tracks. This means the whole SPMO→QQQ overlay's historical backtest (which uses
  VIX at entry throughout) may have been **systematically underpricing premiums** relative
  to what you'd actually pay — worth rerunning the overlay's historical entries with an IV
  shock closer to +15-20% as the realistic case rather than the stress case. This doesn't
  invalidate the strategy (win rate/RoP would just shrink somewhat, and the existing +20%
  IV-shock robustness check already showed it survives), but it's a live, current-day signal
  that the model's default assumption runs optimistic right now.
- **Realized vol *overstates* SMH's real IV by 26 points, the opposite of the assumed
  direction.** SMH just had a sharp move, so trailing realized vol is running hot while the
  options market isn't pricing in that much forward vol. This reverses the caveat above: the
  SMH options research likely **understated** real-world RoP (options actually cost less
  than modeled), not overstated it. Net effect on the SMH options conclusion: still
  positive, probably *more* attractive than the modeled +82% median RoP, though this is a
  single point-in-time snapshot, not a corrected backtest — the realized-vol proxy will
  sometimes run cold relative to real IV too (e.g. right after a calm stretch), so this cuts
  both ways over time and the historical backtest numbers should stand as a base case rather
  than being revised from one day's chain check.
- **Assumed `SPREAD_COST` (0.3%) is far too low for anything except QQQ.** Real spreads were
  6x (QQQ), 43x (GLD), and 25x (SMH) the assumed cost. For QQQ this barely matters (0.3%
  vs actual 1.8% is still small in absolute terms on a $2,700 contract). For GLD and SMH,
  real spread cost alone would eat a meaningful chunk of any edge — another reason GLD's
  rejection stands, and a real reason to be more conservative sizing SMH than the backtest
  alone suggests.

**Takeaway:** this is exactly the kind of check that should run periodically (not just once)
— IV relationships between an underlying and its proxy index drift, and a single day's
snapshot shouldn't be over-interpreted, but it already changed two conclusions (QQQ backtest
may be too optimistic on premium cost; SMH backtest may be too pessimistic) in one run.

### New tool: bootstrap confidence intervals over historical regimes — 2026-07-03

Built `tools/options_bootstrap.py` — the second toolbox priority from the "how do we prove
these strategies are robust" discussion. Every win-rate/median-RoP number so far is a point
estimate from 9-13 historical regimes; this resamples those regimes (with replacement) to
answer two questions: (1) how much could the *observed* stats have differed by chance from
the same-sized sample, and (2) projecting forward, what's the plausible range of outcomes
over the next 5 regimes (compounded capital return at 3% budget/regime).

```
python -m tools.options_bootstrap SPMO GLD SMH
python -m tools.options_bootstrap SMH --horizon 10
```

**Results (10,000 resamples, 5-regime forward horizon):**

| Ticker | Win rate CI | Median RoP CI | 5-regime compounded return (median, 90% CI) | P(losing money over 5) |
|---|---|---|---|---|
| SPMO | [100%, 100%]* | [+32%, +121%] | +12% [+6%, +21%] | 0%* |
| GLD  | [8%, 54%] | [-70%, +37%] | -3% [-10%, +7%] | 71% |
| SMH  | [36%, 91%] | [-17%, +169%] | +15% [-0%, +34%] | 5% |

**Important caveat on the SPMO row (marked \*):** the historical SPMO sample has *zero*
losing regimes (9/9), so a bootstrap resample of that sample can only ever redraw from
all-positive data — it will mechanically report "100% CI: [100%, 100%]" and "P(losing
money) = 0%" no matter how many times you resample. **This is not evidence that SPMO's
options overlay can't lose** — it's a restatement of "we have no historical loss to learn
from," the same small-sample problem `tools.sizing` already flags for Kelly sizing. Read it
as "the bootstrap has nothing informative to say about SPMO's downside," not as "SPMO is
safe." GLD and SMH's CIs are informative precisely because their historical samples contain
real losses to resample from.

**What this confirms:** GLD's rejection is not fragile to sample luck — even the best-case
resample of its historical regimes rarely turns positive (median RoP CI upper bound is only
+37%, well below breakeven-adjusted expectations). SMH's case is genuinely more nuanced than
the single point estimate suggested: a 90% CI on the 5-regime compounded return spans
[-0%, +34%] — attractive expected value, real dispersion, and a non-trivial (though low, 5%)
chance of a net loss over that horizon. That's a more honest way to size conviction than
"64% win rate, +82% median RoP" alone.

### New tool: options-parameter sensitivity (delta x budget heatmap) — 2026-07-03

Built `tools/options_sensitivity.py` — the third toolbox priority, mirroring
`tools/sensitivity.py`'s plateau-vs-isolated-peak MA heatmap but for the options overlay's
own knobs (target delta x budget fraction) instead of MA windows. The options params
(Δ0.50, 5% budget) had only been validated via a full-history sweep, never checked for
neighbor-robustness the way the MA signal is. Also adds a first-half-vs-second-half
regime split as a decay check, since there's no walk-forward OOS split that makes sense for
a risk-sizing knob (unlike MA windows, delta/budget aren't fitted to data).

```
python -m tools.options_sensitivity SPMO GLD SMH
```

**Results (median RoP across the full regime history, grid of Δ ∈ {0.30..0.85} x budget
∈ {1%..20%}):**

| Ticker | Current cell (Δ0.50/5%) | Neighbor verdict | First half | Second half |
|---|---|---|---|---|
| SPMO→QQQ | +45% | PLATEAU (8/8 positive) | +83% | +32% ⚠ declining |
| GLD→GLD  | -55% | **ISOLATED (0/8 positive)** | -61% | -55% |
| SMH→SMH  | +79% | PLATEAU (8/8 positive) | +13% | +120% |

**SPMO/QQQ:** robust to delta/budget choice (whole neighborhood positive), but the edge has
roughly halved over time — median RoP +83% in the first half of history vs +32% in the
second half. Still solidly positive, not a rejection, but worth watching: if a future
options_sensitivity run shows the second-half number continuing to shrink, that's the same
kind of decay warning `tools.sensitivity`'s rolling-Sharpe check gives for the MA signal.

**GLD:** this closes the door on GLD options completely — it's not that Δ0.50/5% happens to
be a bad pick, **every cell in the entire 6x7 grid is negative**. No nearby parameter tweak
rescues it. Reinforces the earlier rejection with the strongest possible confirmation.

**SMH:** also a genuine plateau (robust to parameter choice), but the first/second-half
split is heavily front-loaded toward recent history (+13% → +120%) — almost certainly
reflecting the 2023-2026 AI/semiconductor rally rather than a stable, repeatable edge. Read
the earlier +82% median RoP finding as "very good in the recent super-cycle," not as a
number that should be extrapolated forward at the same magnitude — the bootstrap CI already
captures some of this uncertainty, but this decay check makes the *reason* for the wide CI
more concrete (small sample dominated by one exceptional multi-year stretch).

### New tool: multi-overlay portfolio aggregation — 2026-07-03

Built `tools/portfolio_combined.py` — the fourth and final toolbox priority. Generalizes
`options_backtest.py --combined` (margin + exactly one overlay) to margin + **any number**
of simultaneous options overlays sharing one capital base. Regimes from every overlay are
merged into one chronological queue, so a later overlay's dynamic budget sizing (% of
*current* equity) reflects P&L already realized by an earlier one — necessary now that
there's a real second overlay candidate (SMH) alongside the shipped SPMO→QQQ one. Also
factored the realized-vol IV-proxy logic (previously duplicated in `options_bootstrap.py`
and `options_sensitivity.py`) into a shared `iv_proxy_series()` helper in
`options_chain_check.py` while building this.

```
python -m tools.portfolio_combined                          # margin + shipped SPMO->QQQ overlay only
python -m tools.portfolio_combined --add SMH:0.50:0.03       # + SMH signal -> SMH calls
python -m tools.portfolio_combined --add SMH:0.50:0.03 --no-base
```

**Result — margin + SPMO→QQQ (5% budget) alone:** CAGR 28.0% → 30.9%, Sharpe 0.97 → 1.10,
MaxDD -35.8% → -29.0%. Consistent with the existing single-overlay finding (numbers differ
slightly from the original `options_backtest --combined` table because that used a 3%
budget and less price history; direction and magnitude are consistent).

**Result — margin + SPMO→QQQ + SMH→SMH (3% budget each), same capital base:** CAGR
28.0% → **35.0%** (+7.0%, vs +2.9% for the SPMO/QQQ overlay alone), Sharpe 0.97 → **1.22**,
MaxDD -35.8% → **-26.3%**. Adding the SMH overlay on top of the existing one improves every
metric further — more CAGR lift, better Sharpe, and a *smaller* drawdown than either the
margin-only baseline or the single-overlay case. This directly answers the practical
question that motivated this whole toolbox effort ("how do we use call options to add
leverage/edge without the margin engine's drawdown risk"): running both overlays together
on the same account is a concrete, working way to capture SMH's edge alongside the existing
strategy, with bounded downside on each position.

### Open questions for next session

1. **Exit rules:** currently hold to bear flip. Test: (a) profit target on option (+100% RoP → scale out), (b) time-roll at 60 DTE remaining, (c) roll-up on strength. The 2016–2018 regime peaked mid-way — a trailing stop could capture more.
2. **Entry filter:** enter on regime flip always, or wait N days / filter by VIX level? High-VIX entries had the best returns (2020, 2025) — filtering them out would be wrong.
3. ~~**GLD leg:** GLD has decent options liquidity. Could run a parallel GLD call overlay on GLD's own signal (MA20/100). Not yet tested.~~ **Done, 2026-07-03 — rejected.** See above: GLD's signal produces too many short whipsaw regimes for a 180-day call to survive.
4. **Real execution:** Futu HK options access, contract costs, margin treatment of long calls. Need to verify before committing capital.
5. **Kelly revisit:** once 20+ regimes have accumulated (live + historical), rerun `tools.sizing` — Kelly will become a reliable cross-check on the Calmar-derived sizes.
6. ~~**SMH options sizing:** ... decide whether it becomes a standalone satellite position or gets folded into the existing options tooling as a second signal source.~~ **Partially answered, 2026-07-03** — `tools.portfolio_combined` shows it works well folded in alongside the SPMO/QQQ overlay (CAGR/Sharpe/MaxDD all improve further). Still needs: a real (not realized-vol-proxy) IV check before sizing real capital — `tools.options_chain_check SMH` is the tool for that, and its first run already flagged realized vol as directionally miscalibrated for SMH right now (see above) — and a decision on exact budget fraction, which `tools.sizing`-style analysis hasn't been run for SMH specifically yet.
