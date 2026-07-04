# Call options overlay

Initial research 2026-07-03. All content below is one continuous research thread —
concept through the current shipped implementation.

## Concept

Add long QQQ calls as a convexity kicker on top of the existing 2x margin strategy.
Signal source stays SPMO MA10/200. Buy calls at each bull regime start, close at bear flip.
This is an overlay — the margin leg runs unchanged underneath.

**Why QQQ, not SPMO:**
- SPMO options: 5 expiries only (max ~6.5 months), ATM spreads 17-24%, OI <1000 — too illiquid for systematic use
- QQQ: 28 expiries including LEAPS, ATM spreads <1%, deep OI
- Signal transfer: SPMO signal applied to QQQ gives **88% win rate** vs 62% on SPMO itself. SPMO's duds are factor-rotation events (momentum vs value); the broader market (QQQ) is unaffected.

**Why ATM (Δ0.50), not OTM or deep ITM:**
- Deep ITM (Δ0.85): cheaper leverage but costs $4-8K premium/regime (mostly intrinsic), wins 8/9 but median RoP only +104%
- ATM (Δ0.50): wins **9/9**, median RoP +210%, costs ~$2-3K/regime (before dynamic sizing). IV-shocked (+20%) still 8/9, median +158% — robust
- OTM (Δ0.30): highest headline RoP (+290%) but falls to 6/9 with IV shock and -45% worst regime — too fragile

## Regime statistics (SPMO, 9 regimes since 2016)

| Metric | Value |
|--------|-------|
| Median duration | 221 days |
| Median QQQ return over regime | +14-18% |
| Signal transfer win rate (QQQ) | 88% (8/9 closed regimes positive) |
| Best regime (QQQ) | +54% (2020-2022) |
| Worst closed regime | -3.6% (Feb 2022, 7 days — whipsaw) |
| ATM call during 7-day whipsaw | +12% RoP (still had 5 months of life left) |

## Budget sweep — dynamic sizing (3% of current equity per regime)

The critical insight: **budget must be sized to current portfolio equity, not fixed initial capital.** With fixed $100K sizing, by 2025 the portfolio is $685K but options are still bought at $3K (0.4% of actual capital). Dynamic sizing fixes this and lets option gains compound.

**Margin-only baseline: CAGR 28.0%, Sharpe 0.97, MaxDD -35.8%**

| Budget | CAGR | Sharpe | MaxDD | CAGR lift |
|--------|------|--------|-------|-----------|
| 1% | 28.5% | 1.01 | -32.4% | +0.5% |
| 3% | 29.9% | 1.06 | -27.5% | +1.9% |
| 5% | 31.6% | **1.06** | -22.6% | +3.6% |
| 7% | 33.4% | 1.00 | -22.9% | +5.4% |
| 10% | 36.2% | 0.91 | -23.2% | +8.3% |
| 15% | 42.0% | 0.78 | -23.9% | +14.0% |
| 20% | 48.3% | 0.72 | -26.5% | +20.4% |

**Sharpe sweet spot: 3-5% budget.** Both improve Sharpe above baseline (1.06 vs 0.97) while meaningfully lifting CAGR. MaxDD also shrinks because call gains cushion regime peaks.

**Past 7%:** CAGR keeps rising but Sharpe dips below baseline — option premium draws introduce equity-curve volatility. MaxDD actually ticks back up past 15% (lumpy cash flows at large scale).

**Practical sizing for 10% budget at scale:** by 2026 the portfolio is ~$1M, so 10% = $100K in premium per regime. Real money at risk per entry. Start at 3-5% and scale up as conviction grows.

## IV sensitivity

Rerun with +20% implied vol at entry (i.e., you buy when options are expensive):
- ATM Δ0.50: win rate drops from 9/9 → 8/9, median RoP drops +210% → +158%. Still comfortably positive.
- OTM Δ0.30: drops to 6/9, worst regime -45%. Fragile.
- Conclusion: ATM is robust to expensive entry vol; OTM is not.

## Tool

```
python -m tools.options_backtest                   # per-regime breakdown, all three deltas
python -m tools.options_backtest --combined        # margin + overlay equity curve (ATM, 3%)
python -m tools.options_backtest --sweep           # budget sweep table + chart (ATM default)
python -m tools.options_backtest --delta 0.30 --sweep  # OTM version
```

## Rolling model — key findings, 2026-07-03

Implemented rolling: close at 30 DTE, open a new ATM call. Each regime can span multiple legs (max 150 calendar days per leg = 180-day tenor minus 30-day roll buffer).

**Long regimes have multiple legs:**
| Regime | Duration | Legs | QQQ return | RoP |
|--------|----------|------|------------|-----|
| 2016-2018 | 738 days | 5 | +49.0% | +70% |
| 2020-2022 | 622 days | 5 | +54.1% | +38% |
| 2023-2025 | 659 days | 5 | +15.6% | +26% |

**Last leg of every long regime is a loser.** The regime ends because SPMO is weakening, which means QQQ is also weakening — so the final call leg is entered when the underlying starts to fade. All three 5-leg regimes had a negative or near-zero final leg. This is structural, not bad luck: the exit signal lags price by design (200-day MA). Accept the last-leg loss as the cost of not exiting early and giving up mid-regime gains.

**Short regimes (< 150 days) are single-leg and usually small wins.** The 7-day whipsaw (Feb 2022) returned +12% RoP because the call still had 5 months of life left when it closed — time value wasn't meaningfully damaged.

**Rolling vs non-rolling:** prior single-leg model overstated returns on long regimes by only entering once per regime. The rolling model is correct: it actually trades each leg and compounds properly. Backtest results should only be cited from the rolling model (`run()` now always uses rolling).

**Strategy comparison (3% overlay budget on combined):**
| Strategy | CAGR | Sharpe | MaxDD |
|----------|------|--------|-------|
| Margin only | 28.0% | 0.97 | -35.8% |
| Options-only (10%) | 22.9% | 1.47 | 0.0% |
| Combined (3%) | 34.6% | 0.99 | -27.3% |
| QQQ B&H | 20.5% | 0.95 | -35.1% |

Sweet spot: **combined at 3-5% overlay.** Lifts CAGR +6-8% over margin-only while keeping Sharpe flat and reducing MaxDD by ~8%. Options-only is interesting as a capital-efficient sidecar (zero drawdown) but lower CAGR than combined.

## Risk-adjusted sizing — findings, 2026-07-03

`python -m tools.sizing` shows Calmar ratio (CAGR / |MaxDD|) and Sharpe across budget fractions 1-20%.

**Calmar is the right metric here.** Sharpe penalizes all volatility equally; retail traders care more about drawdowns (margin calls, psychological limits) than upside vol. Calmar captures exactly the tradeoff we care about.

**Kelly is unreliable with 9 regimes.** Historical win rate of 9/9 (all options regimes profitable) gives Gaussian Kelly of 174% and binary Kelly of infinite — both meaningless for sizing. Kelly requires 30+ loss observations to be reliable. Note for the future: as more regimes accumulate, Kelly will converge to something usable.

**Calmar frontier (at $10K capital, ATM Δ0.50):**
| Budget | CAGR | Sharpe | Calmar | MaxDD | Tier |
|--------|------|--------|--------|-------|------|
| 7%  | 31.8% | 1.10 | 1.14 | -27.8% | Conservative (max Sharpe) |
| 15% | 38.4% | 0.87 | 1.29 | -29.8% | Moderate (max Calmar) |
| 20% | 43.7% | 0.80 | 1.22 | -35.9% | Aggressive (max CAGR) |

- Margin-only baseline: CAGR 27.9%, Calmar 0.78, MaxDD -35.8%
- Every budget level from 1% to 20% improves Calmar above baseline
- Calmar peaks at 15% then declines — high option drawdowns at 20% drag it back down
- Calmar 1.5 target not reached in this data; would require higher sample or larger capital effects

**Practical approach:** start Conservative (7%, max Sharpe), scale toward Moderate (15%) after 3+ live regimes confirm live-trading accuracy of the model.

## New underlyings for the call overlay: GLD rejected, SMH works — 2026-07-03

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
the premium to time decay before the underlying makes a real move. The one long 2023-2026
regime (+198% RoP) rescues the average but the median is deeply negative. Unlike SPMO→QQQ,
GLD's signal does not transfer to a long-call structure.

**SMH signal (MA50/100) → SMH calls, IV proxy = trailing 21-day realized vol (no listed
gold-style vol index for semiconductors, so realized vol is used directly as a conservative
stand-in — likely *understates* true IV, since options typically carry a premium over
realized, so real-world RoP would run somewhat lower than shown here). **Works.** Win rate
7/11 (64%), median RoP **+82%** — actually higher than the SPMO baseline. Stress-tested with
an IV shock (options priced above realized vol, same robustness check used for the SPMO/QQQ
finding): still 6/11 (55%) win rate and +29% median RoP at a conservative +40% shock.

**Why this matters:** SMH was rejected from the margin engine (see
[etf_candidates.md](etf_candidates.md)) because 2x leverage pushes its 2022 crash past the
-50% drawdown constraint — but a long call's downside is capped at the premium paid, so it
can capture SMH's real momentum edge (established earlier: Sharpe 1.10, the best of any
ticker tested) **without** the unbounded-drawdown problem that blocks margin. This is a
legitimate path to adding SMH's edge to the strategy as a bounded-risk satellite options
position, separate from the margin-based SPMO/GLD legs. Not yet sized or added to any tool
at the time — this was exploratory confirmation that the idea works (real sizing followed,
see "Exit rules, entry filter, and SMH sizing" below).

**Caveat (superseded — see real-chain check below):** realized-vol-as-IV-proxy is a bigger
approximation for SMH than `^VIX`-for-QQQ or `^GVZ`-for-GLD (both are actual listed
implied-vol indices; SMH's isn't). Originally assumed this meant real premiums would run
*higher* than modeled — checking a live chain shows the opposite is true right now, see
below.

## New tool: validate the pricing model against a real option chain — 2026-07-03

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

## New tool: bootstrap confidence intervals over historical regimes — 2026-07-03

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

## New tool: options-parameter sensitivity (delta x budget heatmap) — 2026-07-03

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

## New tool: multi-overlay portfolio aggregation — 2026-07-03

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

## Exit rules, entry filter, and SMH sizing — 2026-07-03

**1. Exit rules — tested, baseline (hold to bear flip, 30-DTE roll) wins.** Built a
day-by-day path simulator (walks each leg's daily option value via Black-Scholes, using
the same realized-vol-at-each-day methodology the existing exit pricing uses) to test two
alternatives against the shipped baseline, on both SPMO→QQQ and SMH→SMH:

| Variant | SPMO→QQQ median RoP | SMH→SMH median RoP |
|---|---|---|
| Baseline (30 DTE roll, hold to bear flip) | +52% | +82% |
| 60 DTE roll window (longer legs) | +36% | +60% |
| Profit target +50% RoP scale-out | +51% (mean 80%→45%) | +29% (mean 98%→16%) |
| Profit target +100% RoP scale-out | +46% | +58% |
| Profit target +150% RoP scale-out | +66% (mean still lower) | +73% (mean still lower) |

Every alternative underperforms the baseline, and the mean (not just median) tells the
real story: profit-target scale-out triggers on 60-80% of legs at the +50% threshold, but
cutting winners short there sacrifices exactly the convex tail gains (the +200-355% legs
found in SMH, the +210% recent SPMO leg) that this strategy exists to capture — this is a
trend-following, convex-payoff strategy, and profit-taking is structurally at odds with
that. The 60-DTE roll window is worse too: rolling less often means holding through more
of each option's accelerating theta decay before refreshing into a new at-the-money
contract. **Conclusion: keep the existing 30-DTE roll / hold-to-bear-flip design. Don't add
a profit target or a longer roll window.**

**2. Entry filter by VIX/IV level — tested, no filter recommended; corrects an earlier
assumption.** Measured entry-day IV proxy against eventual regime RoP directly (regime-level,
not leg-level) for all 9 SPMO regimes and 11 SMH regimes:
- SPMO: correlation(entry IV, RoP) = **-0.45** — if anything, *lower*-IV entries did better
  (median +125% below-median-IV vs +32% above-median-IV). This is the opposite of an
  earlier informal note ("high-VIX entries had the best returns") — that note likely
  conflated regime-level entry timing with leg-level roll timing within a long multi-leg
  regime (a single VIX reading at regime start isn't representative of a 600+ day regime
  with 5 rolled legs inside it).
- SMH: correlation = **-0.07** (essentially none), though a median split shows the opposite
  direction (+122% above-median vs +13% below-median) — with only 11 points, this is noise,
  not a usable signal.

**Conclusion: no VIX/IV entry filter is justified by this data.** Neither ticker shows a
clean, sample-robust relationship between entry-day IV and eventual regime return — and
SPMO's own data actively argues against "wait for high VIX."

**3. SMH-specific budget sizing — done**, using `tools.portfolio_combined`'s generalized
infrastructure (SMH signal → SMH calls only, no base SPMO/QQQ overlay, same margin legs).
Calmar/Sharpe/CAGR swept 1%-20% budget, same style as the SPMO/QQQ sizing table:

| Budget | CAGR | Sharpe | Calmar | MaxDD |
|--------|------|--------|--------|-------|
| 3%  | 31.7% | **1.13** | 1.01 | -31.4% |
| 15% | 54.9% | 0.85 | **1.64** | -33.4% |
| 20% | 66.8% | 0.82 | 1.62 | -41.1% |

Margin-only baseline: CAGR 28.0%, Sharpe 0.97, Calmar 0.78, MaxDD -35.8%. Every budget level
1%-20% improves both CAGR and Calmar over margin-only, and Sharpe improves at every level up
to 15%. Conservative (best Sharpe): 3%. Moderate (best Calmar): 15% — notably a *higher*
Calmar than the SPMO/QQQ overlay's own sizing result (1.64 vs 1.29 at 15%), reinforcing SMH
as a strong overlay candidate. Aggressive (best CAGR): 20%.
