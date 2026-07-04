# Strategy experiments

Standalone strategy variants tested against CLAUDE.md's "Options strategies on the SPMO
bull signal" roadmap list, plus one genuinely different momentum family (sector rotation).

## Roadmap options strategies tested: spreads and covered calls rejected, bear puts shipped — 2026-07-03 / 2026-07-06

Tested three of the six roadmap options strategies with real data, rolling 30-DTE mechanics
matching the shipped overlay's methodology (see [options_overlay.md](options_overlay.md)).

**1. Bull call spread (buy ATM + sell OTM call) — rejected.** Tested wide (Δ0.50/0.30) and
narrow (Δ0.50/0.40) spreads against the naked ATM call on both SPMO→QQQ and SMH→SMH:

| | Naked call | Spread (wide) | Spread (narrow) |
|---|---|---|---|
| SPMO→QQQ total P&L | **+$52,543** | +$52,065 | +$47,120 |
| SMH→SMH total P&L | **+$83,148** | +$56,720 | +$49,140 |

The naked call wins on total dollar P&L in both cases (despite the spread's occasionally
higher *median* RoP, since RoP is measured on a smaller premium base) — the short leg caps
exactly the rare monster-move legs (SMH's +305%/+355% legs, SPMO's multi-year runs) that
drive most of the strategy's total return. The cap costs more than the premium it saves,
because this strategy's edge is convexity-dependent, not a case where capping tail risk is
a good trade.

**2. Covered calls on the margin leg — rejected.** Sold monthly Δ0.30 OTM calls against the
full 2x-leveraged SPMO notional, 99 monthly cycles across the margin equity curve's history.
Result: CAGR 28.0% → **26.7%** (-1.2%), Sharpe 0.97 → 0.91, MaxDD **-35.8% → -42.2%** (worse,
not better, despite the usual intuition that covered calls reduce risk). 46% of cycles were
assigned (capped); the worst single cycle (SPMO +14.5% in one month, April 2026) cost
**-$173,912** on its own — a big enough single loss to outweigh dozens of small premium
wins from choppy/flat months. Same root cause as the spread rejection: this strategy's
expected value is concentrated in rare large up-moves, and selling calls against the
position caps exactly those.

**3. Sell cash-secured puts during bear regimes — originally tested ad-hoc, 2026-07-03;
shipped as a real tool `tools/bear_put_overlay.py`, 2026-07-06.** Sold monthly Δ-0.30 OTM
puts on QQQ during all 9 SPMO bear stretches (32 monthly cycles total), using a new
`_get_bear_regimes()` helper (inverse of `_get_regimes`, now a real function in
`tools/options_backtest.py`, tested to be an exact partition of the timeline with the bull
extractor). Unlike items #1/#2, this doesn't cap an existing winning position's upside — it's
a standalone premium-harvesting overlay during periods the strategy is already out of the
market.

**Shipped numbers (own capital-scaled sizing, `--combined`):** CAGR 28.0% → **28.1%**
(+0.2%), Sharpe 0.97 → 0.98, MaxDD **-35.8% → -41.1%** (worse, not the roughly-flat -36.5%
the original informal test found). Standalone (`tools.bear_put_overlay`, $100K flat
capital per regime): 9/9 bear regimes traded, 32 cycles, 25% assignment rate — both numbers
match the original ad-hoc test exactly — **+28% net on premium** ($88,409 premium,
$+24,474 P&L).

**Why the combined MaxDD differs from the original informal number:** the shipped tool sizes
each cycle's premium to `budget_frac` of *current portfolio equity* (same dynamic-sizing
discipline used everywhere else in this project, see [options_overlay.md](options_overlay.md)),
not a fixed dollar budget. By the time the 2022 bear stretch arrives the portfolio is much
larger, so assignment payouts during that regime are proportionally larger too — a real
effect of using the project's standard sizing convention, not a bug. Read the shipped
-41.1% as the more trustworthy number; the original -36.5% was a smaller, informal test that
didn't use equity-proportional sizing.

**Extension tested: SMH signal → SMH puts — rejected, 2026-07-06.** Tried the identical
mechanism on SMH's own bear regimes (11 regimes, 36 cycles). Result: net **-5% on premium**
standalone (one regime, 2018-2019, lost **-395%** of its premium — a Δ-0.30 put still gets
blown through when the underlying is this volatile), and combined with the margin legs,
MaxDD balloons to **-65.2%** (from -35.8% baseline) for only **+0.1%** CAGR lift. Sharpe
actually drops (0.97 → 0.83). This is the same "too volatile for this mechanism" conclusion
as SMH's margin-engine rejection (see [etf_candidates.md](etf_candidates.md)) and its
covered-call-equivalent risk (item #2 above), now confirmed for a third options structure:
SMH's edge only survives in a strictly long, capped-downside form (the naked call overlay),
never in anything that sells premium against its own volatility.

Real tail risk in a sharp, sustained bear market remains for the QQQ version even though it
shipped positive — 2022 was the roughest historical test case and it held up, but a
longer/deeper bear regime than any seen 2016-2026 could look worse, and the SMH result above
is a concrete demonstration of what "worse" can look like on a more volatile underlying.

## Sector rotation (cross-sectional relative strength) — a genuinely different momentum family, 2026-07-03

Everything tested in this project so far is single-ticker time-series/absolute momentum
(MA crossover: is this ticker trending vs its own history). Tested the other classic
momentum family — cross-sectional/relative-strength sector rotation — for comparison: rank
9 SPDR sector ETFs (XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB) by trailing return each
month, hold the top N, rebalance monthly, no leverage.

**Caveat on methodology:** the first pass produced absurd results (CAGR 900%-2300%,
Sharpe 3-4.6) — a real bug, not a finding: the monthly-frequency equity curve was fed
directly into `core.metrics.calc()`, which assumes daily-frequency data and annualizes by
dividing return-count by 252, badly over-annualizing a ~120-point monthly series. Fixed by
reindexing the monthly curve to daily frequency (forward-fill) before computing metrics.
Flagging this because it's exactly the kind of silent bug that would corrupt a real backtest
if not caught by a sanity check on the output magnitude.

**Real results (10.4 years, vs SPY buy & hold CAGR 15.2%, Sharpe 0.88, MaxDD -33.7%):**

| Lookback | Top-N | CAGR | Sharpe | MaxDD | vs SPY CAGR |
|---|---|---|---|---|---|
| 3mo | 1 | 11.9% | 0.66 | -21.1% | -3.3% |
| 3mo | 3 | 14.2% | 0.91 | -18.6% | -1.0% |
| 6mo | 1 | 13.2% | 0.70 | -17.1% | -2.0% |
| 6mo | 3 | 11.6% | 0.79 | -15.2% | -3.6% |
| 12mo | 1 | 16.5% | 0.80 | -17.6% | +1.3% |
| 12mo | 3 | 14.2% | **0.98** | -15.8% | -1.0% |

**Conclusion:** every variant roughly halves SPY's drawdown (-15% to -21% vs -33.7%) with
CAGR in the same ballpark as buy-and-hold (slightly below for most variants, slightly above
for 12-month/top-1). Best risk-adjusted variant is 12-month lookback, top-3 (Sharpe 0.98 >
SPY's 0.88). This is a genuinely different strategy shape than everything else in this
project: a **lower-volatility, lower-drawdown alternative** at 1x exposure, not a
higher-return leveraged play. Not yet tested: whether layering the same 2x-when-confirmed
leverage mechanism established elsewhere in this project on top of sector rotation would
turn "comparable CAGR, better Sharpe/drawdown" into genuine outperformance — a natural next
step if this strategy family gets pursued further. Not yet added to the portfolio or given
its own tool; this is exploratory confirmation the strategy family works reasonably, not a
recommendation to deploy it.
