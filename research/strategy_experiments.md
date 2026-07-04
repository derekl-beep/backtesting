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

**Conclusion (superseded — see below):** every variant roughly halves SPY's drawdown (-15% to
-21% vs -33.7%) with CAGR in the same ballpark as buy-and-hold. This full-period, in-sample
table was flagged at the time as "exploratory confirmation, not a recommendation to deploy"
— building it into a real, walk-forward-validated module (below) shows the in-sample picture
was optimistic in exactly the way `tools.optimize`'s IWM lesson warned about (see
[etf_candidates.md](etf_candidates.md)): full-period alpha that doesn't survive genuine OOS
testing.

## Sector rotation, validated: walk-forward OOS underperforms SPY, not statistically significant — 2026-07-06

Promoted the exploratory backtest above into `tools/sector_rotation.py` — a real module with
the same rigor gauntlet every other strategy in this project has been run through: walk-
forward OOS param selection (same discipline as `tools.optimize`: pick the (lookback, top_n)
combo with the best Sharpe using only data through the prior year, then evaluate OOS), a
permutation significance test (the cross-sectional analog of `tools.significance` — the null
is "N random tickers each month" instead of "random timing of the same exposure"), and the
open leverage-layering question actually tested.

**Building this caught a real, subtle bug before it produced a false finding:** the first
draft of the significance test applied the 2x-when-confirmed leverage overlay to the actual
strategy but not to the random-selection null. That comparison came back "CAGR
significant, p=0.000" — which would have been wrong. Leverage mechanically raises CAGR in a
rising market regardless of which tickers get picked (this project's own
[methodology.md](methodology.md) finding, applied here to a new strategy family); the null
has to apply the *identical* per-ticker leverage mechanism or it's comparing a leveraged
result against an unleveraged one, not testing ranking skill. Fixed by precomputing each
window's per-ticker growth factors with leverage applied identically on both sides before
sampling. A regression test (`test_significance_test_null_applies_the_same_leverage_as_actual`)
locks this in.

**Walk-forward OOS results (2018-2026, 9 folds, unleveraged):**

| Year | Selected params | OOS CAGR | OOS Sharpe | OOS MaxDD | vs SPY |
|---|---|---|---|---|---|
| 2018 | 12mo/top-3 | -7.8% | -0.33 | -19.9% | -2.5% |
| 2019 | 3mo/top-1 | 14.5% | 1.06 | -8.9% | -16.8% |
| 2020 | 6mo/top-3 | 28.3% | 0.90 | -31.5% | +11.0% |
| 2021 | 6mo/top-3 | 20.9% | 1.16 | -11.3% | -9.7% |
| 2022 | 6mo/top-3 | 2.4% | 0.22 | -14.5% | +21.2% |
| 2023 | 12mo/top-1 | 8.2% | 0.48 | -18.6% | -18.8% |
| 2024 | 12mo/top-1 | 15.7% | 0.86 | -14.0% | -10.0% |
| 2025 | 12mo/top-1 | 11.4% | 0.68 | -14.1% | -6.9% |
| 2026 | 12mo/top-1 | -5.6% | -0.06 | -23.5% | -26.1% |

Average vs SPY across all 9 folds: **-6.5%/year**. The full-period in-sample table above
looked "comparable to slightly better" than SPY; genuine walk-forward OOS selection (params
chosen using only prior data, never the year being tested) reverses that — sector rotation
underperforms buy-and-hold in 7 of 9 folds. 2020 and 2022 are the only folds where it wins,
both broad-market-stress years where being selectively out of the worst sectors helped, but
that's not enough to make the strategy work on average.

**Significance test (12mo/top-3, 1000 shifts, unleveraged):** actual CAGR 15.8% vs
random-selection median 12.9%, **p=0.118**; actual Sharpe 0.89 vs median 0.75, **p=0.109**.
Neither clears the conventional 0.05 bar — the specific trailing-return ranking rule is not
distinguishable from picking 3 random sector ETFs each month. This is the same pattern
`tools.significance` already found for every time-series MA-crossover ticker tested
(SPMO, GLD, SMH, SOXX, EFA) — extended here to a structurally different (cross-sectional)
momentum mechanism, with the same conclusion.

**Leverage overlay (research/open_questions.md #8 — does 2x-when-confirmed-strong turn
"comparable CAGR, better risk profile" into genuine outperformance?): no.** Layering the
usual MA10/100-confirmed 2x leverage onto each held ticker (full-period, unleveraged
12mo/top-3 baseline CAGR 15.8% → **24.1%** leveraged, Sharpe roughly flat 0.89 → 0.88, MaxDD
worse -30.3% → -37.4%) raises absolute CAGR the same way leverage always does in this
project, but the walk-forward OOS picture doesn't improve in the way that would matter:
average OOS vs SPY narrows from -6.5%/year to **-3.5%/year**, still negative, while
individual-fold MaxDD gets meaningfully worse (-43.5% in 2026, -38.9% in 2020, vs -23.5% and
-31.5% unleveraged). And once the significance-test null is given the identical leverage
mechanism (the bug-fix above), the leveraged version isn't significant either: p=0.179
(CAGR), p=0.313 (Sharpe).

**Conclusion: rejected, both leveraged and unleveraged.** Sector rotation is a genuinely
different momentum mechanism from everything else in this project, but rigorous validation
— not just the full-period in-sample table — shows it underperforms simple SPY buy-and-hold
out-of-sample and isn't statistically distinguishable from random sector selection. Layering
this project's leverage mechanism on top doesn't fix the underlying OOS weakness; it just
adds absolute return and drawdown in the same "leverage-timing effect, not signal skill"
pattern documented in [methodology.md](methodology.md). Closes Roadmap open question #8.
