# Quant rigor toolbox

Three ticker-agnostic statistical tools built 2026-07-03 to answer "how do we prove these
strategies are actually robust, not just curve-fit or lucky" — plus the probabilistic
regime signal, which asked whether a genuinely different (soft, confidence-scaled) signal
could beat the hard MA flip. All four connect back to [methodology.md](methodology.md)'s
core finding.

## New tool: probabilistic regime signal — tested, does not improve on the hard flip — 2026-07-03

Built `tools/regime_probability.py` — every signal in this project is a hard binary flip
(MA10 > MA200 → 2x, else 1x) — one day fully levered, the next (if the MA crosses) not,
exactly the mechanism behind whipsaw stretches like Feb 2022's 7-day regime. Fit a logistic
regression (implemented from scratch via `scipy.optimize`, no new dependency) on three
simple technical features — MA gap %, RSI(14), MACD histogram — against the sign of the
forward 21-day return, walk-forward (expanding window, same discipline as `tools.optimize`)
so there's no lookahead. Compares scaling leverage continuously with confidence (quantized
to 0.25 increments to keep rebalancing realistic) against the existing hard threshold.

```
python -m tools.regime_probability SPMO GLD SMH
```

**Model fit — in-sample accuracy 65-72% for SPMO/SMH (real, better than a 50% coin flip),
but the OOS probability distribution is narrow across all three tickers:**

| Ticker | OOS probability mean / std / range |
|---|---|
| SPMO | 0.69 / 0.07 / [0.56, 0.90] |
| GLD  | 0.51 / 0.05 / [0.39, 0.65] — nearly uninformative, centered at 50/50 |
| SMH  | 0.71 / 0.10 / [0.44, 0.99] — widest range of the three |

**Strategy comparison — continuous confidence-scaling does not improve on the hard
threshold for any of the three tickers:**

| Ticker | | CAGR | Sharpe | MaxDD | Leverage changes |
|---|---|---|---|---|---|
| SPMO | Hard | 30.5% | 0.94 | -39.7% | 14 |
| SPMO | Continuous | 31.5% | 0.92 | -50.4% | 27 |
| GLD  | Hard | 25.4% | 0.95 | -39.6% | 20 |
| GLD  | Continuous | 20.3% | 0.93 | -35.6% | 9 |
| SMH  | Hard | 41.8% | 0.89 | -60.0% | 21 |
| SMH  | Continuous | 38.4% | 0.84 | -69.3% | 122 |

SPMO and SMH both show *worse* Sharpe and *worse* MaxDD under continuous scaling — the model's
probabilities don't swing decisively low during real drawdowns (the narrow-range finding
above), so the confidence-scaled leverage fails to de-risk as sharply as the hard 2x/1x flip
does when it actually matters. SMH's case is the clearest: even with its widest probability
range of the three, continuous scaling is worse on every metric *and* generates 6x more
leverage changes (122 vs 21) — a high-volatility name crosses quantization boundaries far
more often, meaning the "smoother" approach is paradoxically choppier in practice. GLD is
the one partial exception (better MaxDD, but lower CAGR and Sharpe, and its probability model
is barely informative at 0.51 mean/0.05 std to begin with, so this may just be noise).

**Conclusion:** rejected as implemented. This adds a third independent angle to
[methodology.md](methodology.md)'s finding and `tools.significance`'s result below: a
from-scratch statistical model fit directly to simple technical features also can't extract
a probability signal discriminating enough to beat the simple hard threshold. Doesn't rule
out a better model (different features, different horizon, an HMM instead of logistic
regression) doing better — but this first, reasonably-principled attempt didn't.

## New tool: Value at Risk / Conditional VaR — 2026-07-03

Built `tools/tail_risk.py`, layered directly on `tools.monte_carlo`. Every risk metric in
this project until now is Sharpe (penalizes upside and downside vol symmetrically — wrong
for a strategy built on convex payoffs) or MaxDD (one historical data point, silent about a
future worse than what's already happened). VaR answers "there's a P% chance of losing more
than X"; CVaR (Expected Shortfall) goes further — "*given* we're past that threshold, what's
the average loss," the metric real risk desks actually size capital against because it
captures severity, not just frequency.

**Two views:** historical daily VaR/CVaR on the actual deployed strategy's equity curve
(backward-looking, no model assumptions), and forward-looking VaR/CVaR on the Monte Carlo
simulated distribution (both GBM and block bootstrap) — on total return over the horizon,
and separately on max drawdown, at 95% and 99% confidence.

```
python -m tools.tail_risk SPMO GLD SMH
```

**Results (5yr horizon, 300 sims/method for the Monte Carlo side):**

| Ticker | Historical daily 95% VaR/CVaR | Historical daily 99% VaR/CVaR | MC MaxDD 95% VaR/CVaR (GBM) | MC MaxDD 99% VaR/CVaR (GBM) |
|---|---|---|---|---|
| SPMO | 3.3% / 5.2% | 6.2% / 8.7% | 59.1% / 62.4% | 65.8% / 68.0% |
| GLD  | 2.7% / 4.4% | 5.6% / 7.8% | 51.8% / 56.8% | 61.7% / 63.5% |
| SMH  | 5.6% / 8.4% | 9.5% / 13.5% | **75.1% / 79.3%** | **82.1% / 82.7%** |

**SMH's tail is the standout, consistent with every prior finding about it.** Daily VaR/CVaR
run ~1.7-2x SPMO/GLD's, and forward MaxDD VaR/CVaR sit firmly in "would definitely breach
the -50% margin constraint" territory even at the *median* simulated future, let alone the
tail — third independent confirmation (bootstrap → Monte Carlo → now VaR/CVaR) that SMH's
volatility profile can't run under the margin engine at any reasonable confidence level.

**A real statistical caveat this tool surfaces explicitly, not just in a footnote:** 99% VaR/
CVaR needs far more Monte Carlo samples than 95% to be stable — the 1% tail of 300
simulations is only ~3 observations, too few to trust. The tool prints an explicit warning
whenever the 99% tail sample count is too small, rather than silently reporting a noisy
number as if it were reliable (defaults to 800 sims for this reason). Also found the same
"negative VaR" case the Monte Carlo tool surfaced (SMH block-bootstrap, 95% total return):
the worst 5% of simulated 5-year outcomes is *still a net gain* — a legitimate result, just
one that needs explicit "gain, not a loss" labeling so it doesn't read as broken output.

## New tool: Monte Carlo forward simulation — 2026-07-03

Built `tools/monte_carlo.py`. `tools/options_bootstrap.py` resamples the *exact* 9-13
historical regimes, so it can only ever produce recombinations of what actually happened;
it can't imagine a bear market worse than 2022 or a whipsaw stretch worse than Feb 2022.
This tool instead calibrates a return-generating model to history and simulates thousands
of synthetic *forward* price paths, running the real MA-crossover + leverage logic against
each one.

**Two methods, run side by side as an honest model-risk check:** GBM (i.i.d. daily
log-returns drawn from a fitted Normal — simple, but no fat tails or trend persistence) and
block bootstrap (resamples overlapping ~21-day blocks of real historical daily returns —
preserves fat tails and trend persistence, no parametric assumption, but can only recombine
historical block-level behavior). Each synthetic path is prefixed with real historical data
to warm up the MA windows before the simulated segment is scored.

```
python -m tools.monte_carlo SPMO GLD SMH --horizon 5
```

**Results (5-year horizon, 300 sims/method):**

| Ticker | Method | CAGR median (5-95pct) | MaxDD median | MaxDD worst-5% | P(loss) |
|---|---|---|---|---|---|
| SPMO | GBM | +26.4% (-1.3%, +74.4%) | -41.9% | -58.7% | 6% |
| SPMO | Block | +29.4% (+2.5%, +67.1%) | -41.2% | -58.5% | 3% |
| GLD | GBM | +15.1% (-3.3%, +47.4%) | -35.8% | -51.4% | 10% |
| GLD | Block | +15.9% (-4.3%, +43.5%) | -35.2% | -50.7% | 9% |
| SMH | GBM | +46.7% (-0.7%, +150.1%) | -57.4% | -74.8% | 5% |
| SMH | Block | +51.8% (+6.6%, +133.3%) | -55.2% | -74.9% | 3% |

**SPMO and GLD:** the two methods broadly agree (median CAGR gap <1-3%), giving more
confidence in the forward risk picture. Both show plausible ranges around the historical
numbers, with worst-case (5th percentile) MaxDD somewhat deeper than anything in the
specific 2016-2026 historical path — exactly the point of simulating beyond exact history.

**SMH: methods diverge (auto-flagged, median CAGR gap 5.1%), and the tail is severe.**
Worst-5% MaxDD hits **-75%** under both methods — notably worse than any single historical
SMH regime (worst seen historically was around -60%, per the earlier drawdown-constraint
rejection). This is independent confirmation, via a completely different method (forward
simulation vs regime-level bootstrap), of the same conclusion reached earlier: SMH's
volatility profile is too severe for the margin engine's constraints, and even satellite/
options exposure should size for tail scenarios worse than anything actually observed
2016-2026, not just the historical worst case.

**Interesting nuance:** block bootstrap consistently shows *less* downside than GBM (lower
P(loss), similar-or-better worst-case MaxDD) despite preserving fat tails GBM lacks — likely
because it also preserves real trend persistence/autocorrelation, which a trend-following
MA-crossover signal actually benefits from (GBM's i.i.d. draws create choppier, less
coherent "trends" that confuse the crossover into extra whipsaws). Neither method is "the
answer" alone; where they agree is more trustworthy than either individually, and where
they diverge (SMH) is itself a signal to size conservatively.

## New tool: statistical significance of MA-crossover timing — 2026-07-03

Built `tools/significance.py` — every finding in this log until now compares point
estimates, never asks whether the specific timing chosen by the MA crossover beats *random*
timing of the same amount of leverage exposure, or whether the historical numbers could be
luck plus a rising market.

**Method:** circular-shift permutation test. Rotate the signal's 0/1 regime pattern by a
random number of days (wrapping around) — this preserves the exact regime-block-length
distribution and total time levered, randomizing only *when* those blocks land on the
calendar. Run the same leverage strategy against each shift; the fraction of random shifts
that do at least as well as the actual timing is a one-sided p-value. Validated on synthetic
data first: a hand-built series with a genuine, strong block-aligned edge scores p<0.10
(confirms the method has real power), before trusting it on real tickers.

```
python -m tools.significance SPMO GLD SMH
```

**Results (1000 shifts):**

| Ticker | Actual CAGR | CAGR percentile | p (CAGR) | Actual Sharpe | Sharpe percentile | p (Sharpe) |
|---|---|---|---|---|---|---|
| SPMO (MA10/200) | 29.3% | 66th | 0.344 | 0.94 | 92nd | 0.082 |
| GLD (MA20/100)  | 20.4% | 88th | 0.124 | 0.78 | 83rd | 0.170 |
| SMH (MA50/100)  | 58.2% | 85th | 0.152 | 1.10 | 90th | 0.104 |

**None of the three tickers show p<0.05 significance on CAGR or Sharpe.** SPMO's timing
sits at only the 66th percentile of random-timing CAGR outcomes (p=0.344) — more than a
third of random shifts of the *same* regime-block structure do at least as well. Sharpe
p-values run consistently lower than CAGR p-values across all three (0.082, 0.170, 0.104),
suggesting the specific timing helps smooth volatility somewhat more than it boosts raw
return, but none clear the conventional 0.05 bar; SPMO's Sharpe result (p=0.082) is the
closest to borderline-significant of the nine numbers tested.

Rerun 2026-07-04 on the new candidates found in this session: SOXX p=0.136 (CAGR)/0.103
(Sharpe), EFA p=0.208/0.161 — both also not significant, extending the pattern to every
ticker tested in this project so far.

**What this means:** this goes a level deeper than [methodology.md](methodology.md)'s
"reported alpha is a leverage-timing effect" finding. That finding established the edge
comes from *adding leverage during confirmed uptrends* rather than from stock-picking skill.
This test asks whether the *specific* MA rule's timing choice is better than other timing of
the same exposure fraction — and the honest answer, with the sample size available (~10
years, effectively 9-13 quasi-independent regime events), is: not clearly. A large share of
the strategy's edge may come simply from the *fact* of having a reasonably-distributed on/off
leverage schedule during a period of generally positive drift, not from this exact rule's
predictive skill over alternative timings.

**Important caveat on the null's strength:** circular shift is a relatively generous null —
it only tests "this timing vs other timing of the same block-length distribution," not
"timing vs no timing at all" (that's the separate, already-answered question from
[methodology.md](methodology.md): 1x cash-timing loses to buy-and-hold, so *some* timing
discipline plus leverage is doing real work vs a naive always-2x approach). It also inherits
the small-sample problem that already limits Kelly and the options bootstrap in this log —
with only ~9-13 regimes, statistical power is genuinely limited, and this should be read as
"we can't yet distinguish this rule from noise," not "this rule is definitely noise."
