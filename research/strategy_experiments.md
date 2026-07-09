# Strategy experiments

Standalone strategy variants tested against CLAUDE.md's "Options strategies on the SPMO
bull signal" roadmap list, plus two genuinely different strategy families (sector rotation,
RSI-band mean reversion).

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

## RSI-band mean reversion for rejected macro/EM ETFs: mostly rejected, two inconclusive positives — 2026-07-06

Closes the Roadmap's "Mean-reversion for ETFs" idea. Every ticker tested here (EWJ, EEM,
TLT, GDX, SLV, DBC, VNQ, HYG, FXI, EWZ) was already rejected under MA-crossover momentum
with near-zero or negative alpha (see [etf_candidates.md](etf_candidates.md)) — the
hypothesis was that these don't trend cleanly enough for a momentum signal, but might have
tradeable mean-reverting swings instead.

**Built:** `signals/rsi_band.py` (stateful latch: enter on an oversold RSI dip, hold until
RSI clears the overbought band — deliberately hysteretic so it doesn't flip right at the
entry threshold), `strategies/mean_reversion.py` (1x in-trade / 0x cash, **no persistent 2x
leverage** — mean-reversion is a lower-conviction, shorter-duration trade than the momentum
strategy, so it doesn't carry margin), and `tools/mean_reversion.py` (walk-forward OOS param
selection over a 4×4 oversold/overbought grid, same discipline as `tools.optimize`, plus a
circular-shift significance test reimplemented locally since `tools.significance` is
hardcoded to MA-crossover + the momentum strategy).

**Real bug caught and fixed while building this:** `signals/rsi.py`'s `_rsi()` computed
RSI=0 (maximally *oversold*) for a lookback window with zero losses (an uninterrupted
uptrend) — exactly backwards; the correct value is RSI=100 (maximally *overbought*). The old
code replaced a zero *loss* with infinity before dividing (`gain / loss.replace(0, inf)`),
which computes `gain/inf → 0`, the opposite of letting RS itself go to infinity. Fixed by
letting the division produce its natural inf/nan and handling the true zero-gain-and-zero-
loss case (a perfectly flat window) as neutral (50) instead — see `tests/test_rsi.py` for
the regression tests. This bug pre-dated this session's work and silently affected every
existing user of `signals.rsi._rsi()`: `signals/rsi.py`'s own threshold `signal()` (used
by `tools.optimize --signals rsi`, `tools.compare`, and conditionally `tools.signal`/
`tools.portfolio` for any ticker with an `"rsi"` param — none currently, since the live
SPMO/GLD portfolio is MA-only) and `tools/regime_probability.py`'s RSI feature. Practical
impact on already-published findings is expected to be small: the bug only fires when a full
14-day window has zero down days, rare in real daily price data (confirmed by rerunning the
walk-forward table below before and after the fix — only one fold, VNQ 2026, changed by a
few points). No golden test pinned the old (wrong) behavior, so nothing needed updating
beyond the fix itself.

**Walk-forward OOS results (avg vs buy-and-hold across 9 folds, 2018-2026):**

| Ticker | Avg OOS vs B&H | Most consistent params |
|---|---|---|
| DBC | -11.1% | RSI14 30/75 (6/9 folds) |
| SLV | -7.0% | RSI14 20/65 (7/9 folds) |
| GDX | -4.9% | RSI14 20/65 (5/9 folds) |
| VNQ | -4.9% | RSI14 20/75 (3/9 folds) |
| EEM | -3.0% | RSI14 20/65 (7/9 folds) |
| EWJ | -1.3% | RSI14 25/65 (6/9 folds) |
| EWZ | -0.4% | RSI14 30/75 (8/9 folds) |
| HYG | +0.4% | mixed, no clear winner |
| TLT | **+4.8%** | mixed 20/65 & 25/65 (4/9 each) |
| FXI | **+7.0%** | RSI14 20/65 (7/9 folds) |

**Significance test (circular shift, 1000 shifts, on the two positive standouts):**
- TLT: actual CAGR 5.9% vs random-timing median 4.2%, **p=0.153**; actual Sharpe 0.98 vs
  median 0.84, **p=0.334**.
- FXI: actual CAGR 8.2% vs random-timing median 4.5%, **p=0.109**; actual Sharpe 0.58 vs
  median 0.40, **p=0.161**.

Neither clears the conventional 0.05 bar. Both are directionally the best of the batch and
FXI in particular shows unusually consistent param selection (RSI14 20/65 picked in 7 of 9
folds) — genuinely more interesting than the other 8 tickers — but "best of a batch of 10"
and "statistically significant" are different claims, and this is the same "indistinguishable
from random timing of the same exposure" verdict `tools.significance` already found for every
MA-crossover ticker tested (SPMO, GLD, SMH, SOXX, EFA) and `tools.sector_rotation` found for
cross-sectional selection.

**Conclusion: mostly rejected.** 8 of 10 candidates show flat-to-negative OOS alpha under
RSI-band mean reversion, confirming the "these tickers don't trend cleanly enough for MA
crossover" diagnosis doesn't automatically imply "so a contrarian signal must work instead" —
mean reversion isn't a free alternative hypothesis, it has to earn its own validation the
same way momentum did. TLT and FXI are the two exceptions worth remembering if either shows
up again in future research (e.g. if bond or China-exposure ETFs get revisited), but neither
is strong enough evidence on its own to add either to the deployed strategy set today.

## Volatility-targeted continuous leverage (2026-07-09) — rejected

**Hypothesis (scoped in [open_questions.md](open_questions.md) #15):** every strategy in
this repo uses discrete leverage (0x/1x/2x) gated by the trend signal. Does replacing the
fixed 2x-when-confirmed with continuous leverage scaled against trailing realized volatility
— `leverage = clip(target_vol / realized_vol, floor, cap)`, still gated by the same unchanged
MA-crossover regime (1x hold in bear) — improve risk-adjusted return or reduce drawdown
versus holding a flat leverage through the whole bull regime? This is mechanically different
from the rejected `tools.regime_probability` (which tried to predict *direction*): vol-
targeting doesn't predict anything, it risk-manages an already-confirmed trend.

Built as `strategies/vol_target.py` (`positions()` — `core/simulator.py::run` already treats
`positions` as continuous target leverage per day, so no simulator change was needed) and
`tools/vol_target.py` (walk-forward OOS over a window×target_vol×cap grid, same discipline
as `tools.optimize`, `floor` fixed at 1.0).

**The comparison that matters:** a vol-targeting strategy that simply runs at a lower average
leverage than a fixed 2x will look "safer" for free — that's not evidence vol-scaling helps,
it's just less leverage (the same fairness bug class caught in `tools/sector_rotation.py`,
see `docs/agents/LESSONS.md` 2026-07-06). So every OOS fold is compared against a
**matched-average-leverage baseline**: `strategies.momentum` run at a *fixed* leverage equal
to the vol-targeting strategy's own realized average leverage over that same fold — both
sides carry identical average exposure, only whether *scaling by vol* helps is being tested.

**Significance test:** a circular-shift of the regime signal would re-test "does the trend
timing predict direction" — already answered by `tools.significance` and unchanged here
(the regime gate is untouched). The actual new question is whether assigning higher leverage
to specifically low-vol days beats an arbitrary assignment of the same leverage values across
the same bull days. The null permutes the realized leverage values among bull-regime days
only (bear days fixed at 1x) — identical average exposure, identical regime structure, only
which day gets which value is randomized.

**Walk-forward OOS results, 9 folds (2018-2026), on the two live legs:**

| Ticker | Avg selected leverage | Avg Sharpe (vol-target − matched baseline) | Avg vs B&H CAGR |
|---|---|---|---|
| SPMO | ~1.0-1.3x | **-0.07** | -0.3% |
| GLD  | ~1.0-1.2x | **-0.01** | +1.5% |

The walk-forward optimizer never selects params that push average leverage much past ~1.3x
on either ticker — both ETFs' realized volatility is high enough relative to the target-vol
grid that the scaling rule mostly sits near its 1x floor, rarely approaching the 2.0-3.0x cap.
Sharpe improvement over the matched-average-leverage baseline is a wash on both (essentially
0, slightly negative on SPMO).

**Significance test (full-period params, 1000 bull-day permutations):**
- SPMO (win20 tgt15% cap2.5x, avg leverage 1.22x): CAGR p=0.262 (not significant); Sharpe
  p=0.070 (borderline).
- GLD (win10 tgt15% cap3.0x, avg leverage 1.19x): CAGR p=0.205 (not significant); Sharpe
  p=0.069 (borderline).

Neither CAGR result clears p<0.05, and the fact that both tickers land at nearly the same
borderline Sharpe p-value (~0.07) independently is worth noting but not over-reading — with
only ~40 ideas tested project-wide (see `research/methodology.md`'s multiple-testing
addendum), two borderline results are not evidence of a real effect on their own.

**Conclusion: rejected.** Vol-scaled continuous leverage does not improve risk-adjusted
return over a fixed-leverage baseline carrying the identical average exposure, on either live
leg, and the day-to-day leverage assignment isn't statistically distinguishable from a random
assignment of the same values. The mechanism itself worked as designed (confirmed via the
plausibility checks — MaxDD stayed in the range implied by the actual ~1.0-1.3x average
leverage used, not the 2x range, since the optimizer never chose to lever up much); it simply
didn't add value here. Unlike sector rotation and most mean-reversion candidates, this was a
genuinely different mechanism (risk-management, not direction-prediction) — its rejection is
a real, informative negative result, not a rehash.
