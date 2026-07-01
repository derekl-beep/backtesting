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

## Signal configs

### MA+RSI+MACD vs MA-only — rejected (pre-2026)

Multi-signal combos were tested for SPMO. Result: 5x more trades, no net improvement in OOS CAGR after fees. MA-only is simpler and survives costs better.

**Conclusion:** Default to MA-only. Only revisit multi-signal if a ticker shows clear single-signal weakness across multiple OOS folds.
