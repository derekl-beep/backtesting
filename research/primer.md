# Quant Research Primer: How to Build a Profitable Trading Strategy

Written for someone new to quant research and trading. This is the general pipeline
professional quant researchers use, with pointers to where this exact repo already
implements each step — so you can see each stage produce real output rather than just
reading about it.

## The mindset shift first

The hardest part of quant research isn't finding a pattern that "worked" historically —
with enough parameters, you can always find one. The job is **trying to disprove your own
idea** before you trust it. Most of the steps below exist to catch yourself fooling
yourself, not to find new ideas.

## Step 1: Start with a *reason*, not a pattern

Before touching data, ask: **why would this make money?** Real edges usually come from one
of three places:

- **A risk premium** — you're compensated for bearing a risk others avoid (e.g. selling
  options: buyers overpay for insurance against crashes, so sellers collect a premium on
  average — this repo's options overlays exploit exactly this).
- **A behavioral bias** — investors systematically under- or over-react (e.g. momentum:
  stocks that have gone up keep going up for a while because investors under-react to good
  news, then eventually overreact — this repo's core SPMO/GLD strategy).
- **A structural constraint** — some participants *can't* act on the opportunity (e.g.
  institutional mandates preventing them from holding small/volatile names).

If you can't articulate why an inefficiency would exist and persist, you're about to
data-mine, not research. ("This 47-day moving average worked great from 2019-2021" is a
pattern, not a reason.)

## Step 2: Define the universe and get clean data

Decide what you're trading (one ticker? a basket? which asset class?) and get reliable
historical price data. Watch for:

- **Survivorship bias** — testing only on tickers that still exist today silently excludes
  everything that went bankrupt or got delisted, inflating your results.
- **Adjusted vs. unadjusted prices** — dividends/splits must be accounted for or your
  returns are wrong.

(This repo's `core/data.py` handles adjusted-close caching from yfinance for exactly this
reason.)

## Step 3: Turn your idea into precise, mechanical rules

"Buy when it's trending up" isn't testable. "Buy when the 10-day moving average crosses
above the 200-day moving average" is. Every rule needs an exact entry condition, exit
condition, and position size — no ambiguity, no discretion, so a computer (and a future
you) can run it identically every time.

(`signals/ma.py` is a 4-line example: `1 when fast MA > slow MA, else 0`.)

## Step 4: Build a realistic backtest

Simulate the rule against history, but include the friction that makes paper profits
evaporate in real life: trading fees/commissions, bid-ask spread, borrowing costs if you use
leverage or margin, and slippage. A strategy that's profitable before costs and
unprofitable after costs is not a strategy — leaving this out is the single most common way
beginners fool themselves.

(`core/simulator.py` models margin borrow cost and per-trade fees day-by-day, not just a
clean equity curve.)

## Step 5: Resist the in-sample trap

If you tune your rule's parameters (which moving averages? what threshold?) by looking at
the *entire* history and picking whatever performed best, you've just curve-fit to noise —
you're guaranteed a great-looking backtest with no guarantee it means anything going
forward. This project has been burned by exactly this twice historically (see
[../docs/agents/LESSONS.md](../docs/agents/LESSONS.md)).

## Step 6: Walk-forward validation — the real test

The fix: pick parameters using only *past* data, then test on a *future* period the
parameter choice never saw, then roll forward and repeat. This mimics how you'd actually
have to trade — you never get to peek at the future when deciding today's parameters.

(`tools.optimize`: picks MA windows using data through year N-1, tests on year N, then rolls
forward year by year from 2018 to today.)

## Step 7: Ask "or was this just luck?" — significance testing

Even a random strategy can look good in one specific historical window by chance. A real
test: does your *specific* rule beat *random* timing of the same amount of market exposure?
Shuffle the timing (keeping everything else identical) many times and see what fraction of
random shuffles do as well as your actual rule. If 30% of random shuffles beat your
"strategy," you haven't found anything.

(`tools.significance` does exactly this with 1,000 randomized shuffles per ticker — and
notably, in this repo, *no* ticker has ever cleared the conventional significance bar, which
is an important, honest finding in itself, not a failure. See
[methodology.md](methodology.md).)

## Step 8: Check robustness, not just the best result

Look at the parameter *neighborhood*, not just the single best value. If MA(10,200) looks
great but MA(9,200) and MA(11,200) both look terrible, that's a red flag (an isolated lucky
spike, not a real effect) — a genuine effect usually looks good across a plateau of nearby,
reasonable parameters.

(`tools.sensitivity` produces exactly this kind of heatmap.)

## Step 9: Sanity-check the magnitude

If your backtest says 400% annual returns, you've almost certainly got a bug (wrong data
frequency, look-ahead bias, a leverage calculation error), not a discovery. Keep a mental
table of "what's actually plausible" for the kind of strategy you're running, and treat
anything outside it as guilty until proven innocent.

(This repo's [../docs/agents/JUDGMENT.md](../docs/agents/JUDGMENT.md) §6 keeps exactly this
table, seeded from real bugs it already caught this way.)

## Step 10: Risk and position sizing — often matters more than the signal

Even a real edge can ruin you with bad sizing. Decide: how much capital per trade, how much
leverage (if any), and what drawdown you can actually tolerate psychologically and
financially before you'd panic-sell at the worst time. A mediocre signal with disciplined
sizing usually beats a great signal with reckless sizing.

(`tools.sizing` does this for the options overlay: Calmar/Sharpe across budget fractions,
with three sizing tiers.)

## Step 11: Paper trade before risking real money

Run the strategy live, on paper (or tiny size), for a while before committing meaningful
capital. This catches the gap between "backtest assumptions" and "real execution" — real
fills, real data delays, real emotions.

## Step 12: Monitor and know when to stop

Markets change. Re-check your strategy periodically against the same tests above. Decide in
advance what would make you stop trading it (a sustained underperformance vs. expectations,
a structural change in the market) — deciding this *before* you're down money is much easier
than deciding it in the moment.

## The honest bottom line

Most ideas, tested rigorously through this pipeline, don't survive — and that's normal, not
a failure of the process. This repo's own research log is mostly *rejected* ideas (sector
rotation, most mean-reversion candidates, covered calls, vol-targeting — see
[README.md](README.md) for the full index) tested exactly this way, which is actually the
sign the process is working, not that nothing here is any good.

## Common pitfalls, summarized

| Pitfall | What it looks like | Where this repo guards against it |
|---|---|---|
| Look-ahead bias | Signal uses information not actually available on that date | Signals compute on data available as-of that day only |
| Survivorship bias | Universe only includes tickers that still exist today | N/A for a fixed 2-ticker portfolio; matters more when screening new candidates |
| In-sample curve-fitting | Best full-period parameter table treated as a finding | `tools.optimize` walk-forward folds; JUDGMENT.md §7 rubric |
| Ignoring transaction costs | Backtest profitable before fees, not after | `core/config.py` fee constants baked into `core/simulator.py` |
| Data-mining / multiple testing | Testing 40 ideas and reporting the one that "worked" | `methodology.md`'s multiple-testing addendum — 1 hit in ~40 attempts is expected noise, not a discovery |
| Unfair null/baseline | Comparing a leveraged strategy against an unleveraged benchmark | `tools.sector_rotation`'s significance test bug + fix, documented in LESSONS.md |
| Implausible results treated as real | A 900% CAGR reported without question | JUDGMENT.md §6 plausibility table |
