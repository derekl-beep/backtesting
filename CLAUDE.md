# SPMO + GLD Portfolio — Agent Guide

Momentum margin strategy backtester for a two-ETF portfolio: SPMO 80% + GLD 20%.
Primary use cases: daily signal checks, backtesting, parameter optimization, portfolio analysis.

## Environment

```bash
.venv/bin/python -m tools.signal SPMO GLD   # run directly, no activation needed
```

## Current portfolio

| Ticker | Weight | Signal | OOS folds | Avg vs B&H |
|--------|--------|--------|-----------|------------|
| SPMO   | 80%    | MA10/200       | 5/8 | +13.0% |
| GLD    | 20%    | MA20/100       | 5/8 | +13.0% |

Weights + signal params live in **one place**: `PORTFOLIO` in `core/portfolio_config.py`.
Both `tools/portfolio.py` (backtests) and `tools/signal.py` (live checks) import from it,
and `tools.tune --apply` rewrites it.

## Tests

```bash
.venv/bin/pytest
```
Run after any change to `core/`, `signals/`, or `strategies/`. The suite pins exact
signal flips, simulator fee/borrow math, metrics, and an end-to-end golden backtest —
real money follows these numbers, so a failing golden test means the change altered
strategy behavior and must be deliberate.

## Tools

### Check today's signal
```bash
python -m tools.signal SPMO GLD
python -m tools.signal SPMO --capital 50000
python -m tools.signal SPMO GLD --alert              # + machine-readable JSON
python -m tools.signal SPMO GLD --alert --threshold 3
```
Returns: MA/RSI/MACD values per component, combined signal ON/OFF, days in regime,
distance to MA flip, position sizing, last 5 signal flips.

`--alert` appends an `ALERT_STATUS_JSON` block with per-ticker `flipped_today`,
`entered_band_today` (first day inside the near-flip threshold — fires once, not
daily), `days_in_band`, and yesterday's distance. Used by the daily cloud routine
so alerts stay stateless and deduplicated.

When multiple tickers are passed, appends a **PORTFOLIO SUMMARY** block showing the
combined margin state: ALL ON / ALL OFF / MIXED with per-leg weights and total deploy
amount. Use this to answer: "should I be in margin today?", "how close is SPMO to flipping?"

### Backtest a single ETF
```bash
python -m tools.backtest SPMO
python -m tools.backtest SPMO QQQ SPY
```
Returns: lifetime summary (CAGR, Sharpe, max drawdown, fees) + year-by-year table.
Saves chart to `charts/backtest/backtest_results_YYYY-MM-DD.png`.

Uses each ticker's MA params from `PORTFOLIO` in `core/portfolio_config.py` (e.g. SPMO →
MA10/200, GLD → MA20/100). Falls back to MA50/100 for tickers not in the portfolio.

### Portfolio backtest
```bash
python -m tools.portfolio
python -m tools.portfolio SPMO:0.8:50:100 GLD:0.2:30:50
```
Format: `TICKER:weight:ma_fast:ma_slow`. Weights must sum to 1.0.

Returns: per-leg stats + portfolio aggregate vs B&H 1x and B&H 2x + year-by-year.
Saves chart to `charts/portfolio/portfolio_results_YYYY-MM-DD.png`.

### ETF screener
```bash
python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM EWJ NUKZ
```
Returns: correlation matrix + per-ticker stats (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD).
Saves chart to `charts/screen/screen_results_YYYY-MM-DD.png`.

Known portfolio tickers (SPMO, GLD) are evaluated at their configured MA params and marked
with ✓. New candidate tickers are screened at MA50/100 as a neutral baseline — run
`python -m tools.optimize <TICKER>` to find their optimal params before adding them.

Use to find low-correlation candidates with positive strategy alpha before adding to portfolio.
EWJ/EEM-type macro ETFs tend to show near-zero alpha — see Roadmap.

### Portfolio tuning (recommended — joint optimization)
```bash
python -m tools.tune              # optimize all tickers jointly, show comparison
python -m tools.tune --apply      # same, but write changes if Sharpe improves
```
Runs portfolio-level walk-forward optimization across all joint MA param combos,
backtests current vs recommended, and gates --apply on Sharpe improvement.

Use this instead of per-ticker optimize when retuning the whole portfolio.
Per-ticker optimize is still useful for screening new ETFs before adding them.

### Per-ticker walk-forward optimization
```bash
python -m tools.optimize SPMO
python -m tools.optimize --signals ma,rsi SPMO
python -m tools.optimize --signals ma,rsi,macd SPMO
python -m tools.optimize --final SPMO      # held-out test — touch once per year
```
Returns: per-fold OOS results, consistency table, recommended params.
OOS folds: 2018–2025. Holdout: 2025–present.

Run on new ETF candidates before screening them into the portfolio.
Pick param with highest fold count; break ties by avg vs B&H CAGR (>5% threshold).
Prefer MA-only over multi-signal unless improvement clearly survives fees.

### Portfolio-level optimizer (standalone)
```bash
python -m tools.portfolio_optimize              # default portfolio
python -m tools.portfolio_optimize SPMO:0.8 GLD:0.2
```
Sweeps 225 joint param combos across all tickers, ranks by portfolio alpha vs B&H.
Use when you want to see the full OOS table without running the tune pipeline.

### Live options trade recommendation
```bash
python -m tools.options_signal
python -m tools.options_signal --capital 150000
python -m tools.options_signal --delta 0.30     # OTM calls instead
```
Returns: SPMO signal state, current bull/bear regime duration, recommended QQQ call
(nearest real expiry ~6 months, ATM strike, estimated premium), contract count at
3/5/10% budget levels, unrealized P&L on the current leg (if mid-regime), and
roll/exit triggers. Use when SPMO is bullish to know exactly what to buy.

### Options backtest
```bash
python -m tools.options_backtest                   # per-regime breakdown, all deltas
python -m tools.options_backtest --combined        # margin + overlay equity curve
python -m tools.options_backtest --options-only    # options-only strategy (no margin)
python -m tools.options_backtest --compare         # all three strategies side-by-side
python -m tools.options_backtest --sweep           # budget fraction sweep table + chart
python -m tools.options_backtest --delta 0.30 --budget 0.05
python -m tools.options_backtest --ticker SMH                    # SMH signal -> SMH calls
python -m tools.options_backtest --options-only --ticker SMH     # + sweep also supported
```
Signal: SPMO MA10/200. Instrument: QQQ calls. Model: rolling at 30 DTE, ATM Δ0.50 default.
Default budget: **5%** (research sweet spot — best Sharpe, Calmar improves over margin-only).
`--ticker` (any ticker's own signal -> own calls) works with the default report and
`--options-only` (with or without `--sweep`). `--combined`/`--compare`/plain `--sweep` are
still SPMO/QQQ-only — use `tools.portfolio_combined`, `tools.sizing --ticker`, and
`tools.options_sensitivity` for the generalized equivalents.
Key finding: 3–5% overlay budget sweet spot (Sharpe improves, MaxDD shrinks). See RESEARCH.md.

### Validate pricing model against a real option chain
```bash
python -m tools.options_chain_check              # QQQ, the shipped overlay underlying
python -m tools.options_chain_check QQQ GLD SMH
python -m tools.options_chain_check SMH --delta 0.30
python -m tools.options_chain_check GLD --tenor 90
```
Pulls the real live option chain nearest the modeled tenor/delta and prints model price/IV
next to the real quote, spread, and open interest. Everything else in `options_backtest.py`/
`options_signal.py` is theoretical Black-Scholes pricing — run this periodically to catch
the proxy IV drifting away from real market pricing. See RESEARCH.md for the first run's
findings (VIX currently underprices QQQ's real IV; realized vol overstates SMH's).

### Bootstrap confidence intervals over historical regimes
```bash
python -m tools.options_bootstrap                  # default: SPMO signal -> QQQ calls
python -m tools.options_bootstrap GLD SMH
python -m tools.options_bootstrap SMH --horizon 10  # project 10 future regimes instead of 5
```
Resamples historical per-regime returns (with replacement) to turn point-estimate win
rate/median RoP into confidence intervals, and projects a forward distribution over the
next N regimes (compounded capital return, P(losing money)). Only 9-13 historical regimes
exist per ticker — treat this as "how much to trust the point estimate," not a guarantee.
**Caveat:** a ticker with zero historical losing regimes (e.g. SPMO, 9/9) will always
bootstrap to a 100% win-rate CI — that reflects an all-positive sample, not proof the
strategy can't lose. See RESEARCH.md for the full readout.

### Options-parameter sensitivity (delta x budget heatmap)
```bash
python -m tools.options_sensitivity                # default: SPMO signal -> QQQ calls
python -m tools.options_sensitivity GLD SMH
```
Grids target delta (0.30-0.85) x budget fraction (1%-20%), evaluated as median RoP across
every historical regime — the options-overlay analog of `tools.sensitivity`'s MA heatmap.
Also splits regime history in half chronologically to flag a decaying edge. First run found
GLD's rejection holds across the *entire* grid (not just the default point), SPMO/QQQ's edge
has roughly halved over time (still positive), and SMH's strong number is front-loaded into
the recent semiconductor rally. See RESEARCH.md for details.

### Multi-overlay portfolio aggregation
```bash
python -m tools.portfolio_combined                       # margin + shipped SPMO->QQQ overlay only
python -m tools.portfolio_combined --add SMH:0.50:0.03    # + SMH signal -> SMH calls
python -m tools.portfolio_combined --add SMH:0.50:0.03 --no-base
```
Generalizes `options_backtest.py --combined` (margin + exactly one overlay) to margin + any
number of simultaneous options overlays sharing one capital base — needed once there's more
than one options position at a time. Regimes from every overlay are merged chronologically
so a later overlay's dynamic budget sizing reflects earlier overlays' realized P&L. First
run: margin + SPMO/QQQ + SMH/SMH together lifts CAGR 28.0%→35.0%, Sharpe 0.97→1.22, and
*reduces* MaxDD to -26.3% (better than margin-only or either overlay alone). See RESEARCH.md.

### Risk-adjusted sizing analysis
```bash
python -m tools.sizing
python -m tools.sizing --delta 0.30     # OTM calls
python -m tools.sizing --capital 150000
python -m tools.sizing --ticker SMH     # size the SMH signal -> SMH calls overlay instead
```
Answers: how much options budget should I use per regime? Shows Calmar ratio (CAGR/|MaxDD|),
Sharpe, and CAGR across budget fractions 1–20%. Derives three sizing tiers:
  - Conservative: budget that maximizes Sharpe
  - Moderate: lowest budget where Calmar ≥ 1.5 (or best available)
  - Aggressive: budget that maximizes CAGR
Also shows a Kelly cross-check with a clear caveat (9 regimes is too few for reliable Kelly
estimates — use Calmar/Sharpe targets as the primary guide). Saves a 4-panel chart to
`charts/sizing_YYYY-MM-DD.png`.

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Returns: side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

### Parameter robustness check
```bash
python -m tools.sensitivity              # all portfolio tickers
python -m tools.sensitivity SPMO
```
Returns: OOS alpha heatmap over the full MA grid (current params outlined — plateau
= robust, isolated peak = curve-fit), neighbor verdict, and rolling 1y Sharpe vs B&H
(decay warning). Charts to `charts/sensitivity/`. Run quarterly or before trusting
newly tuned params.

## Architecture

```
core/
  config.py             shared constants (leverage, fees, margin, dates)
  portfolio_config.py   live portfolio: weights + signal params (single source of truth)
  data.py           yfinance fetch with local cache in data/ (adjusted close;
                    cache valid until the next NYSE close — refetches full history,
                    never tail-appends, because adjusted close rescales retroactively)
  metrics.py        calc(equity) → {cagr, sharpe, max_dd, total}
  simulator.py      run(prices, positions, capital) → {equity, leverage, margin_calls, fees}
signals/
  ma.py             signal(prices, fast, slow) → 0/1 Series
  ma_3tier.py       signal(prices, fast, mid, slow) → 0/1/2 Series
  rsi.py            signal(prices, threshold) → 0/1 Series
  rsi_band.py       signal(prices, period, oversold, overbought) → 0/1 stateful latch
  macd.py           signal(prices, fast, slow, signal) → 0/1 Series
  combo.py          majority_of / all_of / any_of combinators
strategies/
  momentum.py       2x bull / 1x bear  (ETF-style — hold when bearish)
  momentum_cash.py  2x bull / 0x cash  (stock default — exit when bearish)
  momentum_3t.py    2x / 1x / 0x  (three-tier, for stocks only)
  mean_reversion.py 1x in-trade / 0x cash  (RSI band entry/exit)
tools/  (ETF — master branch)
  signal.py              live signal check (params from core/portfolio_config.py)
  options_signal.py      live options trade recommendation (what QQQ call to buy today)
  backtest.py            single-ETF backtest + chart
  portfolio.py           multi-ETF portfolio backtest + chart (params from core/portfolio_config.py)
  options_backtest.py    QQQ call overlay backtest (rolling model, 3 deltas, combined/sweep/compare modes)
  options_chain_check.py validate the BS pricing model against a real live option chain (IV, price, spread, OI)
  options_bootstrap.py   bootstrap confidence intervals over historical regimes (win rate/RoP CI + forward projection)
  options_sensitivity.py delta x budget heatmap + first/second-half decay check for the options overlay
  portfolio_combined.py  margin legs + N simultaneous options overlays on one shared capital base
  sizing.py              risk-adjusted sizing: Calmar/Sharpe vs budget fraction, 3 tier recommendations
  optimize.py            per-ticker walk-forward optimizer
  portfolio_optimize.py  joint portfolio-level optimizer (sweeps all ticker combos together)
  tune.py                end-to-end pipeline: optimize → compare → apply
  screen.py              ETF screener: correlation + strategy stats
  compare.py             multi-strategy comparison
  sensitivity.py         param robustness: OOS heatmap + rolling Sharpe decay
tools/  (stocks — feature/stock-backtesting branch)
  stock_rank.py     daily ranking of watchlist by momentum strength (start here)
  stock_signal.py   live signal + position sizing per stock (STOCK_CONFIGS at top)
  stock_screen.py   momentum-cash vs mean-rev alpha per ticker
  stock_backtest.py per-stock backtest with strategy selection
  stock_portfolio.py N-stock weighted portfolio backtest
  stock_optimize.py walk-forward MA optimizer (--tier 2 default, --tier 3 for 3-tier)
tests/              pytest suite: signals, simulator math, metrics, golden backtest, config invariants
charts/             all generated .png files saved here
```

## Common workflows

**Daily ETF check:**
```bash
python -m tools.signal SPMO GLD
```

**Adding a new ETF to the portfolio:**
1. `python -m tools.screen <TICKER> SPMO` — check correlation and strategy alpha
2. `python -m tools.optimize <TICKER>` — find optimal MA params
3. Update `PORTFOLIO` in `core/portfolio_config.py` (weights must sum to 1.0)
4. `python -m tools.portfolio` — verify combined results

**Running the annual held-out test:**
```bash
python -m tools.optimize --final SPMO
```
Only run once per year — it consumes the holdout period.

**Stock daily workflow (feature/stock-backtesting branch):**
```bash
# 1. Rank watchlist to find today's entry candidates
python -m tools.stock_rank

# 2. Drill into a specific stock for sizing
python -m tools.stock_signal NVDA

# 3. Screen a new stock before adding it
python -m tools.stock_screen NVDA MSFT AAPL TSLA META

# 4. Backtest (default: momentum_cash vs mean_rev side-by-side)
python -m tools.stock_backtest NVDA
python -m tools.stock_backtest NVDA --strategy momentum_cash
python -m tools.stock_backtest NVDA --strategy compare    # momentum_cash vs ETF-style

# 5. Optimize MA params (2-tier default, sweeps fast/slow pairs)
python -m tools.stock_optimize NVDA
python -m tools.stock_optimize --tier 3 NVDA   # 3-tier: sweeps fast/mid, slow=200

# 6. Portfolio backtest
python -m tools.stock_portfolio NVDA MSFT AAPL                   # equal weight
python -m tools.stock_portfolio NVDA:0.5 MSFT:0.3 AAPL:0.2      # specified weights
```

Stock strategies:
- `momentum_cash` (default): 2x when MA_fast > MA_slow, 0x cash when bearish
- `mean_rev`: 1x when RSI < 30 (latch until RSI > 70), 0x cash otherwise
- `momentum` (ETF-style): 2x bullish, 1x hold bearish — avoid for stocks
- Per-ticker configs live in `STOCK_CONFIGS` at top of `tools/stock_signal.py`

## Research log

`RESEARCH.md` — running record of tested ETFs, rejected candidates, and signal config experiments.
Check it before re-testing an idea. Update it whenever a backtest produces a clear finding.

## Roadmap

**Mean-reversion for ETFs** — EWJ/EEM-type macro ETFs show near-zero alpha with MA crossover.
A contrarian RSI or Bollinger Band strategy could capture their moves but requires a separate
signal framework, different position sizing (no persistent 2x leverage), and independent
walk-forward validation. Would be a new strategy module distinct from the stock mean_rev tool.

**Leverage on sector rotation** — cross-sectional relative-strength sector rotation (rank 9
SPDR sectors by trailing return, hold top N, rebalance monthly) was tested 2026-07-03 at 1x
exposure: roughly halves SPY's drawdown with comparable-to-slightly-better Sharpe, but CAGR
is in the same ballpark as buy-and-hold, not the outsized returns the leveraged momentum
strategy shows. Untested: does layering the same "2x when confirmed strong" leverage
mechanism used elsewhere in this project on top of sector rotation turn "comparable CAGR,
better risk profile" into genuine outperformance? See RESEARCH.md for the full backtest.

**Web UI — discussed 2026-07-03, not yet scoped or built.** All tooling today is CLI +
PNG charts + a growing `RESEARCH.md` log. Discussed whether a web UI would help: verdict
was yes, but narrowly — for *checking* things, not for doing research. Concrete slices
worth considering, roughly in priority order:
  1. **Daily signal dashboard** — current signal state, days in regime, distance to flip,
     position sizing, rendered as a page instead of requiring `tools.signal` in a terminal.
     Highest value since it's the most frequent action (checked daily).
  2. **Chart/research browsing** — a searchable/filterable view over the dated PNG charts
     in `charts/` and the findings in `RESEARCH.md`, instead of scrolling files.
  3. **Interactive parameter exploration** — sliders for delta/budget/MA windows that
     recompute `tools.sensitivity`/`tools.options_sensitivity`-style output live, instead
     of re-running CLI flags one at a time.
  Explicitly NOT in scope: replacing the CLI for actual backtesting/research — that's
  faster in code today, and a browser-triggered arbitrary-backtest surface adds security
  considerations without speeding up that loop. If pursued, keep it read-only/reporting,
  not a way to kick off new runs from a browser.

---

### Options strategies on the SPMO bull signal (to backtest)

All of these use the SPMO MA10/200 signal as the entry/exit trigger. Ranked roughly by
implementation complexity, easiest first.

**1. Bull call spread — tested and rejected, 2026-07-03.** Naked ATM call beats both a wide
(Δ0.50/0.30) and narrow (Δ0.50/0.40) spread on total dollar P&L for both SPMO→QQQ (+$52.5K
vs +$52.1K/+$47.1K) and SMH→SMH (+$83.1K vs +$56.7K/+$49.1K) — the short leg caps exactly
the rare monster-move legs that drive most of the strategy's return. See RESEARCH.md.

**2. Covered calls on the margin leg — tested and rejected, 2026-07-03.** Selling monthly
Δ0.30 calls against the 2x SPMO notional made things worse on every metric: CAGR 28.0%→26.7%,
Sharpe 0.97→0.91, MaxDD -35.8%→-42.2% (worse, not better). A single assigned cycle during a
strong up-month cost -$173,912, outweighing dozens of small premium wins. Same root cause as
the spread rejection above. See RESEARCH.md.

**3. Leveraged ETF rotation (TQQQ / UPRO) — tested and rejected, 2026-07-03.** Ran
`tools.screen`/`tools.optimize` directly on TQQQ/UPRO/SOXL: all show strongly negative alpha
vs their own B&H at baseline (-18% to -41%), and none pass the -50% drawdown constraint even
in the first OOS fold (2018 alone produces -53% to -74% MaxDD). Volatility decay from daily
fund rebalancing is fundamentally incompatible with a slow MA-crossover trigger at any
exposure level. See RESEARCH.md for details. Closed — do not revisit without a materially
different (faster/adaptive) signal.

**4. Diagonal spread (poor man's covered call)** — buy deep ITM LEAPS (Δ~0.85, 12–18 month
expiry) as a stock replacement, sell near-term OTM calls monthly against it. LEAPS provide
leveraged long exposure at lower capital than owning shares; short calls fund theta drag.
Requires monthly management. Backtest: model LEAPS purchase at regime start + monthly short
call income; compare net return vs naked long call and margin leg.

**5. Synthetic long (sell ATM put + buy ATM call)** — same strike, same expiry. Net premium
roughly zero (put credit offsets call debit). Gives stock-equivalent exposure with minimal
upfront cost — effectively free leverage when premiums net to zero. Risk: short put has
uncapped downside if regime fails (same concern as naked put selling). Backtest: simulate
entry/exit at regime boundaries; model put assignment risk on losing regimes.

**6. Sell puts during bear regimes — tested, modestly positive, 2026-07-03.** Selling
monthly Δ-0.30 puts on QQQ during all 9 SPMO bear stretches: CAGR 28.0%→28.4%, Sharpe
0.97→1.00, MaxDD roughly flat (-35.8%→-36.5%). Unlike items #1/#2, this doesn't cap an
existing winning position — it's a standalone premium-harvesting overlay during periods
already out of the market. Real but modest; 2022 was the roughest historical test and held
up, though a longer/deeper bear regime than any seen 2016-2026 could look worse. See
RESEARCH.md. Worth adding as a minor enhancement if the operational overhead is acceptable.

**Implementation notes:**
- `tools/options_backtest.py` already has the BS pricer, VIX IV proxy, regime extractor, and
  rolling framework. New strategies extend this file or import from it.
- Bear-regime put selling needs a separate `_get_bear_regimes()` helper (inverse of existing).
- Covered calls need the margin equity curve from `_build_portfolio_equity()` as the base.
