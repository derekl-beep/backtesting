# SPMO + GLD Portfolio — Agent Guide

Momentum margin strategy backtester for a two-ETF portfolio: SPMO 80% + GLD 20%.
Primary use cases: daily signal checks, backtesting, parameter optimization, portfolio analysis.

## Environment

```bash
source .venv/bin/activate   # always activate before running anything
```

## Current portfolio

| Ticker | Weight | Signal | OOS folds | Avg vs B&H |
|--------|--------|--------|-----------|------------|
| SPMO   | 80%    | MA50/100       | 3/4 | +12.5% |
| GLD    | 20%    | MA30/50        | 4/4 | +17.7% |

Signal configs live in two places — **keep in sync**:
- `DEFAULT_PORTFOLIO` in `tools/portfolio.py` (weights + signal params)
- `SIGNAL_CONFIGS` in `tools/signal.py` (same params, used for live checks)

## Tools

### Check today's signal
```bash
python -m tools.signal SPMO GLD
python -m tools.signal SPMO --capital 50000
```
Returns: MA/RSI/MACD values per component, combined signal ON/OFF, days in regime,
distance to MA flip, position sizing, last 5 signal flips.

Use this to answer: "should I be in margin today?", "how close is SPMO to flipping?"

### Backtest a single ETF
```bash
python -m tools.backtest SPMO
python -m tools.backtest SPMO QQQ SPY
```
Returns: lifetime summary (CAGR, Sharpe, max drawdown, fees) + year-by-year table.
Saves chart to `charts/backtest_results.png`.

### Portfolio backtest
```bash
python -m tools.portfolio
python -m tools.portfolio SPMO:0.8:50:100 GLD:0.2:30:50
```
Format: `TICKER:weight:ma_fast:ma_slow`. Weights must sum to 1.0.

Returns: per-leg stats + portfolio aggregate vs B&H 1x and B&H 2x + year-by-year.
Saves chart to `charts/portfolio_results.png`.

### ETF screener
```bash
python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM EWJ NUKZ
```
Returns: correlation matrix + per-ticker stats (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD).
Saves chart to `charts/screen_results.png`.

Use to find low-correlation candidates with positive strategy alpha before adding to portfolio.
EWJ/EEM-type macro ETFs tend to show near-zero alpha — see Roadmap.

### Walk-forward optimization
```bash
python -m tools.optimize SPMO
python -m tools.optimize --signals ma,rsi SPMO
python -m tools.optimize --signals ma,rsi,macd SPMO
python -m tools.optimize --final SPMO      # held-out test — touch once per year
```
Returns: per-fold OOS results, consistency table, recommended params.
OOS folds: 2022–2025. Holdout: 2025–present.

Run before adding a new ETF. Pick param with highest fold count; break ties by avg vs B&H CAGR.
Prefer MA-only over multi-signal unless improvement clearly survives fees.

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Returns: side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

## Architecture

```
core/
  config.py       shared constants
  data.py         yfinance fetch (returns pd.Series of daily close)
  metrics.py      calc(equity) → {cagr, sharpe, max_dd, total}
  simulator.py    run(prices, positions, capital) → {equity, leverage, margin_calls, fees}
signals/
  ma.py           signal(prices, fast, slow) → 0/1 Series
  rsi.py          signal(prices, threshold) → 0/1 Series
  macd.py         signal(prices, fast, slow, signal) → 0/1 Series
  combo.py        majority_of / all_of / any_of combinators
strategies/
  momentum.py     positions(signal, leverage) → leverage Series
tools/
  signal.py       live signal check (SIGNAL_CONFIGS at top — keep in sync with portfolio.py)
  backtest.py     single-ETF backtest + chart
  portfolio.py    multi-ETF portfolio backtest + chart (DEFAULT_PORTFOLIO at top)
  optimize.py     walk-forward optimizer
  screen.py       ETF screener: correlation + strategy stats
  compare.py      multi-strategy comparison
charts/           all generated .png files saved here
```

## Common workflows

**Daily check:**
```bash
python -m tools.signal SPMO GLD
```

**Adding a new ETF to the portfolio:**
1. `python -m tools.screen <TICKER> SPMO` — check correlation and strategy alpha
2. `python -m tools.optimize <TICKER>` — find optimal MA params
3. Update `DEFAULT_PORTFOLIO` in `tools/portfolio.py` and `SIGNAL_CONFIGS` in `tools/signal.py`
4. `python -m tools.portfolio` — verify combined results

**Running the annual held-out test:**
```bash
python -m tools.optimize --final SPMO
```
Only run once per year — it consumes the holdout period.

**Screening stocks (which strategy fits?):**
```bash
python -m tools.stock_screen NVDA MSFT AAPL TSLA META
```
Shows momentum alpha and mean-rev alpha per ticker. Use to decide which strategy to apply.
Trending stocks (large-cap tech) tend to favor momentum; macro/sector stocks may favor mean-rev.

**Backtesting a stock:**
```bash
python -m tools.stock_backtest NVDA                       # both strategies side-by-side
python -m tools.stock_backtest NVDA --strategy momentum
python -m tools.stock_backtest NVDA --strategy mean_rev
```

**Building a stock portfolio:**
```bash
python -m tools.stock_portfolio NVDA MSFT AAPL                        # equal weight
python -m tools.stock_portfolio NVDA:0.5 MSFT:0.3 AAPL:0.2           # specified weights
python -m tools.stock_portfolio NVDA MSFT AAPL --strategy momentum
python -m tools.stock_portfolio NVDA MSFT AAPL --strategy mean_rev
```

## Roadmap

**Mean-reversion strategy** — ETFs driven by macro/sector rotation (EWJ, EEM) show near-zero
alpha with MA crossover signals. A contrarian RSI or Bollinger Band strategy could capture
these moves but requires a separate signal framework, different position sizing (no persistent
2x leverage), and independent walk-forward validation. Would be a new strategy module.

**Individual stock backtesting** — Reuse `core/` and `signals/` infrastructure; add stock-specific
tools alongside existing ETF tools. New modules: `tools/stock_screen.py` (large-universe screener,
hundreds of tickers), `tools/stock_backtest.py` (per-stock with strategy selection),
`tools/stock_portfolio.py` (N-stock dynamic allocation), `strategies/mean_reversion.py`.
ETF workflow stays untouched.
