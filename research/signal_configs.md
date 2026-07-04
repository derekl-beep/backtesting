# Signal configs

## Extended history + alpha filter — params unchanged, 2026-07-01

Extended backtest history from 2020 to 2016 (SPMO launch), giving 8 OOS folds (2018-2025) vs 4 previously. Also fixed a tie-breaking bug in the optimizer (was picking by insertion order; now breaks ties by avg vs B&H). Added `MIN_AVG_ALPHA = 5%` filter to exclude params that pass constraints but don't meaningfully beat B&H.

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

## MA+RSI+MACD vs MA-only — rejected (pre-2026)

Multi-signal combos were tested for SPMO. Result: 5x more trades, no net improvement in OOS CAGR after fees. MA-only is simpler and survives costs better.

**Conclusion:** Default to MA-only. Only revisit multi-signal if a ticker shows clear single-signal weakness across multiple OOS folds.

## Sensitivity heatmap baseline — 2026-07-01

First run of `python -m tools.sensitivity` (new tool: full MA grid evaluated directly
on all 8 OOS folds, per ticker).

**SPMO (current MA10/200):** on a plateau — every grid cell passes 8/8 folds with
positive alpha — but in the weakest column (+1.5% avg OOS alpha vs +9-10% for the
MA*/100 column). This is the per-ticker view of the known joint-optimizer tradeoff:
MA10/200 trades per-ticker alpha for fewer trades/fees and better portfolio Sharpe
(see "Extended history + alpha filter" entry). Not a red flag, but if the portfolio
context changes (e.g. GLD removed), revisit the /100 column.

**GLD (current MA20/100):** mid-plateau, +7.3% avg OOS alpha, all 8 neighbors
positive (+3.1% to +11.7%). Robust.

**Rolling 1y Sharpe gap (strategy - B&H):** SPMO full-history -0.17, last year -0.37;
GLD -0.17 / -0.08. Negative full-history gaps are expected (the strategy wins on
drawdown/total-return compounding, not per-period Sharpe); watch for the SPMO gap
widening further.
