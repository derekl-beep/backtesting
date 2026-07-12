# Methodology: reported "alpha" is a leverage-timing effect, not signal quality

*2026-07-03*

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
message, easy to mistake for "not enough data." Fixed: prints an explicit
`SKIPPED — no combo passed constraints...` line instead of just omitting rows.

## Independent confirmations of this finding

Three separate methods, built and run independently, all agree with this conclusion:

1. **This entry** — direct 1x-vs-2x decomposition on SPMO/GLD.
2. **`tools.significance`** (circular-shift permutation test, see [quant_toolbox.md](quant_toolbox.md)) —
   none of SPMO/GLD/SMH show p<0.05 significance vs random timing of the same exposure.
3. **`tools.regime_probability`** (from-scratch logistic regression, see [quant_toolbox.md](quant_toolbox.md)) —
   a model fit directly to technical features also can't extract a probability signal
   discriminating enough to beat the simple hard MA threshold.

When reading any new candidate's screener/optimizer output (see
[etf_candidates.md](etf_candidates.md)), apply this same lens: a big "alpha" number means
"this ticker's volatility profile can support 2x leverage-timing without breaching -50%
drawdown," not "this signal has genuine predictive skill."

## Addendum 2026-07-09 — multiple-testing caution

Roughly 40 signal/strategy/ticker ideas have now been tested against a p<0.05 significance
bar across this log. At that rate, pure chance predicts ~2 false positives even if nothing
here has real skill. The fact that **zero** have ever cleared p<0.05 is reassuring — it means
the "everything is leverage-timing" conclusion isn't an artifact of stopping at a lucky
result. But it cuts the other way too: if a future test ever *does* clear p<0.05, treat it
with **extra** skepticism (rerun on a fresh ticker/period, re-derive the null by hand) rather
than as the first real signal — one hit in ~40 attempts is exactly what a false positive
looks like.
