# Tool Reference

Full catalog of every CLI tool in this repo. Extracted from CLAUDE.md 2026-07-07 so the
router stays small — read this file when you need to *run* something, not by default.

All commands run without venv activation:

```bash
.venv/bin/python -m tools.<name> [args]
```

Findings and verdicts referenced below live in `research/` (start at `research/README.md`).
This file tells you **how to run tools**; it does not own research conclusions.

## Task index

| I want to… | Tool |
|---|---|
| Check today's margin signal | `tools.signal` |
| Know what QQQ call to buy today | `tools.options_signal` |
| Backtest one ETF | `tools.backtest` |
| Backtest the whole portfolio | `tools.portfolio` |
| Screen a new ETF candidate | `tools.screen`, then `tools.optimize` |
| Retune the whole portfolio's params | `tools.tune` |
| Optimize one ticker's MA params (OOS) | `tools.optimize` |
| Check params aren't curve-fit | `tools.sensitivity` |
| Backtest the call-options overlay | `tools.options_backtest` |
| Validate option pricing vs real quotes | `tools.options_chain_check` |
| Size an options budget | `tools.sizing` |
| Run several overlays on one capital base | `tools.portfolio_combined` |
| Test statistical significance of timing | `tools.significance` |
| Simulate forward scenarios | `tools.monte_carlo` |
| Measure tail risk (VaR/CVaR) | `tools.tail_risk` |
| Bootstrap CIs on options regimes | `tools.options_bootstrap` |
| Options delta×budget robustness | `tools.options_sensitivity` |
| Compare signal combos for a ticker | `tools.compare` |
| Sell puts in bear regimes (overlay) | `tools.bear_put_overlay` |
| Annual held-out test (once/year only!) | `tools.optimize --final` |

Tools for strategies that were tested and **rejected** (kept for reproducibility — do not
build on them without reading the rejection first): `tools.sector_rotation`
([research/strategy_experiments.md](../research/strategy_experiments.md)),
`tools.mean_reversion` (mostly rejected, same file), `tools.regime_probability`
([research/quant_toolbox.md](../research/quant_toolbox.md)).

---

## Daily operation

### Check today's signal — `tools.signal`
```bash
.venv/bin/python -m tools.signal SPMO GLD
.venv/bin/python -m tools.signal SPMO --capital 50000
.venv/bin/python -m tools.signal SPMO GLD --alert              # + machine-readable JSON
.venv/bin/python -m tools.signal SPMO GLD --alert --threshold 3
```
Returns: MA/RSI/MACD values per component, combined signal ON/OFF, days in regime,
distance to MA flip, position sizing, last 5 signal flips.

`--alert` appends an `ALERT_STATUS_JSON` block with per-ticker `flipped_today`,
`entered_band_today` (first day inside the near-flip threshold — fires once, not daily),
`days_in_band`, and yesterday's distance. Used by the daily cloud routine so alerts stay
stateless and deduplicated.

With multiple tickers, appends a **PORTFOLIO SUMMARY** block: ALL ON / ALL OFF / MIXED with
per-leg weights and total deploy amount. Use this to answer "should I be in margin today?"

### Live options trade recommendation — `tools.options_signal`
```bash
.venv/bin/python -m tools.options_signal
.venv/bin/python -m tools.options_signal --capital 150000
.venv/bin/python -m tools.options_signal --delta 0.30     # OTM calls instead
```
Returns: SPMO signal state, regime duration, recommended QQQ call (nearest real expiry
~6 months, ATM strike, estimated premium), contract counts at 3/5/10% budget, unrealized
P&L on the current leg, roll/exit triggers. Use when SPMO is bullish.

---

## Backtesting

### Single ETF — `tools.backtest`
```bash
.venv/bin/python -m tools.backtest SPMO
.venv/bin/python -m tools.backtest SPMO QQQ SPY
```
Lifetime summary (CAGR, Sharpe, MaxDD, fees) + year-by-year table. Chart to
`charts/backtest/backtest_results_YYYY-MM-DD.png`. Uses each ticker's MA params from
`PORTFOLIO` in `core/portfolio_config.py`; falls back to MA50/100 for unknown tickers.

### Portfolio — `tools.portfolio`
```bash
.venv/bin/python -m tools.portfolio
.venv/bin/python -m tools.portfolio SPMO:0.8:50:100 GLD:0.2:30:50
```
Format: `TICKER:weight:ma_fast:ma_slow`; weights must sum to 1.0. Per-leg stats +
aggregate vs B&H 1x and B&H 2x + year-by-year. Chart to `charts/portfolio/`.

### Strategy comparison — `tools.compare`
```bash
.venv/bin/python -m tools.compare SPMO
```
Side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.
⚠ Known issues (crash on SH fetch failure; chart saved to repo root + `plt.show()`) — see
[docs/agents/DIAGNOSIS.md](agents/DIAGNOSIS.md) "Known doc-vs-code discrepancies".

### ETF screener — `tools.screen`
```bash
.venv/bin/python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM EWJ NUKZ
```
Correlation matrix + per-ticker stats (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD).
Chart to `charts/screen/`. Portfolio tickers are evaluated at their configured params
(marked ✓); new candidates use MA50/100 as a neutral baseline. Use to find low-correlation
candidates with positive alpha before adding to the portfolio. Read
[research/methodology.md](../research/methodology.md) before interpreting "alpha".

---

## Optimization & validation

### Portfolio tuning (preferred for retuning) — `tools.tune`
```bash
.venv/bin/python -m tools.tune              # optimize all tickers jointly, show comparison
.venv/bin/python -m tools.tune --apply      # same, but write changes if Sharpe improves
```
Portfolio-level walk-forward optimization across joint MA combos; backtests current vs
recommended; `--apply` is gated on Sharpe improvement and rewrites
`core/portfolio_config.py`. Use this, not per-ticker optimize, when retuning the whole
portfolio (per-ticker optima proved fragile at portfolio level — see
[research/signal_configs.md](../research/signal_configs.md)).

### Per-ticker walk-forward optimization — `tools.optimize`
```bash
.venv/bin/python -m tools.optimize SPMO
.venv/bin/python -m tools.optimize --signals ma,rsi SPMO
.venv/bin/python -m tools.optimize --signals ma,rsi,macd SPMO
.venv/bin/python -m tools.optimize --final SPMO      # ⚠ held-out test — once per YEAR only
```
Per-fold OOS results (folds 2018–2025), consistency table, recommended params. Run on new
candidates before adding. Pick the param with the highest fold count; tie-break by avg vs
B&H CAGR (>5% threshold). Prefer MA-only over multi-signal unless the improvement clearly
survives fees. `--final` consumes the 2025–present holdout — never run it casually.

### Joint optimizer (standalone table) — `tools.portfolio_optimize`
```bash
.venv/bin/python -m tools.portfolio_optimize              # default portfolio
.venv/bin/python -m tools.portfolio_optimize SPMO:0.8 GLD:0.2
```
Sweeps 225 joint param combos, ranks by portfolio alpha vs B&H. Use to see the full OOS
table without the tune pipeline.

### Parameter robustness — `tools.sensitivity`
```bash
.venv/bin/python -m tools.sensitivity              # all portfolio tickers
.venv/bin/python -m tools.sensitivity SPMO
```
OOS-alpha heatmap over the full MA grid (current params outlined — plateau = robust,
isolated peak = curve-fit), neighbor verdict, rolling 1y Sharpe vs B&H (decay warning).
Charts to `charts/sensitivity/`. Run quarterly and before trusting newly tuned params.

---

## Statistical rigor suite

Full findings for all four tools: [research/quant_toolbox.md](../research/quant_toolbox.md).

### Significance of signal timing — `tools.significance`
```bash
.venv/bin/python -m tools.significance              # all portfolio tickers
.venv/bin/python -m tools.significance SPMO GLD SMH
.venv/bin/python -m tools.significance SMH --resamples 5000
```
Circular-shift permutation test: does this MA window beat *random timing of the same
exposure*, or is it luck plus a rising market? Verdict to date: no ticker tested clears
p<0.05. Run on any new signal/ticker before believing its backtest.

### Monte Carlo forward simulation — `tools.monte_carlo`
```bash
.venv/bin/python -m tools.monte_carlo SPMO GLD SMH
.venv/bin/python -m tools.monte_carlo SMH --horizon 10 --resamples 2000
```
GBM + block-bootstrap synthetic forward paths, actual strategy scored against each —
explores tails worse than anything historical. Where the two methods disagree, trust
neither and size conservatively.

### VaR / CVaR — `tools.tail_risk`
```bash
.venv/bin/python -m tools.tail_risk SPMO GLD SMH
```
Historical daily VaR/CVaR on the deployed equity curve + forward-looking on the Monte
Carlo distribution (total return and MaxDD, 95%/99%). Warns when too few sims exist for a
stable 99% tail.

### Probabilistic regime signal — `tools.regime_probability` (rejected)
```bash
.venv/bin/python -m tools.regime_probability SPMO GLD SMH
```
Walk-forward logistic regression P(bull) with continuous leverage scaling. **Tested and
rejected** — worse than the hard MA flip on all portfolio tickers. Kept for reproducibility.

---

## Options overlay suite

Full research thread: [research/options_overlay.md](../research/options_overlay.md).
Shipped default: SPMO MA10/200 signal → QQQ calls, rolling at 30 DTE, ATM Δ0.50, 5% budget.

### Overlay backtest — `tools.options_backtest`
```bash
.venv/bin/python -m tools.options_backtest                   # per-regime breakdown, all deltas
.venv/bin/python -m tools.options_backtest --combined        # margin + overlay equity curve
.venv/bin/python -m tools.options_backtest --options-only    # options-only (no margin)
.venv/bin/python -m tools.options_backtest --compare         # all three side-by-side
.venv/bin/python -m tools.options_backtest --sweep           # budget sweep table + chart
.venv/bin/python -m tools.options_backtest --delta 0.30 --budget 0.05
.venv/bin/python -m tools.options_backtest --ticker SMH                    # SMH signal → SMH calls
.venv/bin/python -m tools.options_backtest --options-only --ticker SMH     # + sweep supported
```
`--ticker` works with the default report and `--options-only`; `--combined`/`--compare`/
plain `--sweep` are SPMO/QQQ-only — use `tools.portfolio_combined`, `tools.sizing --ticker`,
and `tools.options_sensitivity` for generalized equivalents.

### Pricing-model validation — `tools.options_chain_check`
```bash
.venv/bin/python -m tools.options_chain_check              # QQQ, the shipped underlying
.venv/bin/python -m tools.options_chain_check QQQ GLD SMH
.venv/bin/python -m tools.options_chain_check SMH --delta 0.30
.venv/bin/python -m tools.options_chain_check GLD --tenor 90
```
Pulls the real live option chain nearest the modeled tenor/delta; prints model price/IV vs
real quote, spread, open interest. Everything else in the options tools is theoretical
Black-Scholes — run this periodically to catch proxy-IV drift.

### Bootstrap confidence intervals — `tools.options_bootstrap`
```bash
.venv/bin/python -m tools.options_bootstrap                  # default: SPMO signal → QQQ calls
.venv/bin/python -m tools.options_bootstrap GLD SMH
.venv/bin/python -m tools.options_bootstrap SMH --horizon 10
```
Turns point-estimate win rate/median RoP into CIs + a forward distribution. ⚠ A ticker with
zero historical losing regimes (e.g. SPMO 9/9) mechanically bootstraps to a 100% win-rate
CI — that means "no loss data to learn from," not "can't lose."

### Delta × budget sensitivity — `tools.options_sensitivity`
```bash
.venv/bin/python -m tools.options_sensitivity                # default: SPMO signal → QQQ calls
.venv/bin/python -m tools.options_sensitivity GLD SMH
```
Grids target delta (0.30–0.85) × budget (1–20%), median RoP per cell, plus a first/second
half chronological split to flag a decaying edge.

### Multi-overlay aggregation — `tools.portfolio_combined`
```bash
.venv/bin/python -m tools.portfolio_combined                       # margin + shipped overlay
.venv/bin/python -m tools.portfolio_combined --add SMH:0.50:0.03    # + SMH signal → SMH calls
.venv/bin/python -m tools.portfolio_combined --add SMH:0.50:0.03 --no-base
```
Margin legs + any number of simultaneous options overlays on one shared capital base;
regimes merged chronologically so later overlays' dynamic sizing sees earlier P&L.

### Bear-regime put selling — `tools.bear_put_overlay`
```bash
.venv/bin/python -m tools.bear_put_overlay                    # SPMO signal → QQQ puts (shipped)
.venv/bin/python -m tools.bear_put_overlay --ticker SMH        # SMH → SMH puts (rejected)
.venv/bin/python -m tools.bear_put_overlay --delta -0.20 --budget 0.05
.venv/bin/python -m tools.bear_put_overlay --combined          # margin + overlay equity curve
```
Sells monthly cash-secured OTM puts (default Δ-0.30) during bearish stretches. SPMO→QQQ
shipped (marginal improvement, worse MaxDD); SMH→SMH rejected. Verdict details:
[research/strategy_experiments.md](../research/strategy_experiments.md).

### Risk-adjusted sizing — `tools.sizing`
```bash
.venv/bin/python -m tools.sizing
.venv/bin/python -m tools.sizing --delta 0.30
.venv/bin/python -m tools.sizing --capital 150000
.venv/bin/python -m tools.sizing --ticker SMH     # size the SMH→SMH overlay instead
```
Calmar/Sharpe/CAGR across budget fractions 1–20%; three tiers (Conservative = max Sharpe,
Moderate = Calmar ≥ 1.5 or best available, Aggressive = max CAGR) + a Kelly cross-check
with explicit small-sample caveat. 4-panel chart to `charts/sizing_<TICKER>_YYYY-MM-DD.png`
(saved in `charts/` root, not a `charts/sizing/` subdir).
⚠ Suspected low-budget rounding issue — see DIAGNOSIS.md discrepancy list.

---

## Rejected-strategy modules (kept for reproducibility)

### Sector rotation — `tools.sector_rotation` (rejected 2026-07-06)
```bash
.venv/bin/python -m tools.sector_rotation                       # backtest at default 12mo/top-3
.venv/bin/python -m tools.sector_rotation --lookback 6 --top-n 1
.venv/bin/python -m tools.sector_rotation --leverage             # + 2x overlay per holding
.venv/bin/python -m tools.sector_rotation --walk-forward         # OOS param selection
.venv/bin/python -m tools.sector_rotation --significance         # permutation test
```
Cross-sectional momentum over 9 SPDR sector ETFs. Walk-forward OOS underperforms SPY by
~6.5%/yr; not significant vs random selection. Do not revisit without a materially
different mechanism. [research/strategy_experiments.md](../research/strategy_experiments.md).

### RSI-band mean reversion — `tools.mean_reversion` (mostly rejected 2026-07-06)
```bash
.venv/bin/python -m tools.mean_reversion                     # all 10 rejected candidates
.venv/bin/python -m tools.mean_reversion EWJ EEM
.venv/bin/python -m tools.mean_reversion TLT --period 21
.venv/bin/python -m tools.mean_reversion FXI --significance   # + circular-shift test
```
Contrarian RSI-band latch (1x in-trade / 0x cash, no leverage) on the 10 macro/EM ETFs
rejected under momentum. 8/10 flat-to-negative OOS; TLT/FXI positive but not significant.
[research/strategy_experiments.md](../research/strategy_experiments.md).

---

## Stock tools (feature/stock-backtesting branch only)

These modules exist on `feature/stock-backtesting`, not `master`. Individual stocks default
to **momentum_cash** (2x bull / 0x cash — exit completely when bearish), unlike ETFs
(2x bull / 1x hold). Per-ticker configs: `STOCK_CONFIGS` at top of `tools/stock_signal.py`.

```bash
.venv/bin/python -m tools.stock_rank                          # 1. rank watchlist (start here)
.venv/bin/python -m tools.stock_signal NVDA                   # 2. drill into one stock
.venv/bin/python -m tools.stock_screen NVDA MSFT AAPL TSLA    # 3. screen new candidates
.venv/bin/python -m tools.stock_backtest NVDA                 # 4. momentum_cash vs mean_rev
.venv/bin/python -m tools.stock_backtest NVDA --strategy compare   # vs ETF-style
.venv/bin/python -m tools.stock_optimize NVDA                 # 5. 2-tier MA optimizer
.venv/bin/python -m tools.stock_optimize --tier 3 NVDA        #    3-tier: fast/mid, slow=200
.venv/bin/python -m tools.stock_portfolio NVDA MSFT AAPL      # 6. equal weight
.venv/bin/python -m tools.stock_portfolio NVDA:0.5 MSFT:0.3 AAPL:0.2
```

---

## Architecture

```
core/
  config.py             shared constants (leverage, fees, margin, dates)
  portfolio_config.py   live portfolio: weights + signal params (SINGLE SOURCE OF TRUTH)
  data.py               yfinance fetch, local cache in data/ (adjusted close; cache valid
                        until next NYSE close — refetches FULL history, never tail-appends,
                        because adjusted close rescales retroactively)
  metrics.py            calc(equity) → {cagr, sharpe, max_dd, total}   ⚠ assumes DAILY data
  simulator.py          run(prices, positions, capital) → {equity, leverage, margin_calls, fees}
signals/                                    (main codebase)
  ma.py                 signal(prices, fast, slow) → 0/1 Series
  rsi.py                signal(prices, threshold) → 0/1 Series
  rsi_band.py           signal(prices, period, oversold, overbought) → 0/1 stateful latch
  macd.py               signal(prices, fast, slow, signal) → 0/1 Series
  combo.py              majority_of / all_of / any_of combinators
strategies/                                 (main codebase)
  momentum.py           2x bull / 1x bear   (ETF-style — hold when bearish)
  mean_reversion.py     1x in-trade / 0x cash (RSI band entry/exit)
  hedged.py             2x bull / rotate into SH hedge when bearish (used by tools.compare)
  put_hedge.py          2x bull / ATM-put hedge + cash when bearish (BS-priced, rolled monthly)
-- branch feature/stock-backtesting ONLY (do not import these on master):
  signals/ma_3tier.py   signal(prices, fast, mid, slow) → 0/1/2 Series
  strategies/momentum_cash.py  2x bull / 0x cash (stock default — exit when bearish)
  strategies/momentum_3t.py    2x / 1x / 0x (three-tier, stocks only)
tools/                  see catalog above
tests/                  pytest suite: signals, simulator math, metrics, golden backtest,
                        config invariants
charts/                 generated .png files (gitignored)
data/                   price cache (gitignored)
```

## Common workflows

**Daily ETF check:**
```bash
.venv/bin/python -m tools.signal SPMO GLD
```

**Adding a new ETF to the portfolio:**
1. `tools.screen <TICKER> SPMO` — correlation + baseline alpha
2. `tools.optimize <TICKER>` — OOS param search
3. `tools.significance <TICKER>` — timing vs random-timing null
4. Update `PORTFOLIO` in `core/portfolio_config.py` (weights sum to 1.0) — **requires
   Derek's approval, see [docs/agents/JUDGMENT.md](agents/JUDGMENT.md) §3**
5. `tools.portfolio` — verify combined results; run `.venv/bin/pytest`

**Testing a new strategy idea:** follow the research-experiment template in
[docs/agents/TEMPLATES.md](agents/TEMPLATES.md) — walk-forward OOS + significance test are
mandatory before any verdict.

**Annual held-out test (once per year, it consumes the holdout):**
```bash
.venv/bin/python -m tools.optimize --final SPMO
```
