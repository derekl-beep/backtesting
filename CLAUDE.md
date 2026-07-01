# SPMO Backtesting — Agent Guide

Momentum margin strategy backtester for ETFs. Primary use case: daily signal checks,
backtesting, parameter optimization, and portfolio analysis.

## Environment

```bash
source .venv/bin/activate   # always activate before running anything
```

## Tools

### Check today's signal
```bash
python -m tools.signal SPMO
python -m tools.signal SPMO --capital 50000
```
Returns: current MA values, signal ON/OFF, days in current regime, % move to flip signal,
last 5 signal flips. With `--capital`: position size in shares and dollars.

Use this to answer: "should I be in margin today?", "how close is SPMO to flipping?"

### Backtest a single ETF
```bash
python -m tools.backtest SPMO
python -m tools.backtest SPMO QQQ SPY     # multiple tickers
```
Returns: lifetime summary (CAGR, Sharpe, max drawdown, fees) + year-by-year table.
Saves chart to `backtest_results.png`.

Strategy: MA50/100 crossover, 2x leverage when bullish, 1x when bearish.

### Portfolio backtest (multi-ETF)
```bash
python -m tools.portfolio
python -m tools.portfolio SPMO:0.5:50:100 VGT:0.25:50:150 VOO:0.25:50:150
```
Format: `TICKER:weight:ma_fast:ma_slow`. Weights must sum to 1.0.

Returns: per-leg stats + portfolio aggregate (CAGR, Sharpe, max drawdown) + year-by-year.
Saves chart to `portfolio_results.png`.

Default portfolio: SPMO 80% (MA50/100), GLD 20% (MA30/50).
Each ticker has its own independently tuned MA params — see `DEFAULT_PORTFOLIO` in
`tools/portfolio.py` for current params and their walk-forward validation notes.

### Walk-forward optimization
```bash
python -m tools.optimize SPMO
python -m tools.optimize VGT VOO           # tune params for new tickers
python -m tools.optimize --final SPMO      # run held-out test (touch once)
```
Returns: per-fold OOS results, consistency table, recommended MA params.
OOS folds: 2022–2025. Holdout: 2025–present.

Run this before adding a new ETF to the portfolio. Take the param with highest
appearances count; break ties by avg vs B&H CAGR.

### ETF screener
```bash
python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM
```
Returns: per-ticker stats table (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD) +
correlation matrix. Saves chart to `screen_results.png` with equity curves, heatmap,
and CAGR bar chart.

Use this to pick ETFs for the portfolio — look for low correlation to SPMO + positive
strategy alpha. MA params default to MA50/100; tune independently before adding to portfolio.

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Returns: side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

## Validated parameters

| Ticker | MA fast | MA slow | OOS folds | Avg vs B&H |
|--------|---------|---------|-----------|------------|
| SPMO   | 50      | 100     | 3/4       | +12.5%     |
| GLD    | 30      | 50      | 4/4       | +17.7%     |

## Configuration (`core/config.py`)

| Key | Value | Notes |
|-----|-------|-------|
| `INITIAL_CAPITAL` | 10,000 | Starting value per backtest |
| `LEVERAGE` | 2.0 | Multiplier when bullish |
| `MARGIN_RATE` | 0.048 | Annual borrow rate (Futu HK USD) |
| `MAINTENANCE_MARGIN` | 0.30 | Margin call threshold |
| `MAX_DRAWDOWN_LIMIT` | -0.50 | Hard constraint in optimization |
| `START` | 2020-01-01 | Historical data start |

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
  signal.py       live signal check
  backtest.py     single-ETF backtest + chart
  optimize.py     walk-forward optimizer
  compare.py      multi-strategy comparison
  portfolio.py    multi-ETF portfolio backtest + chart
```

## Common workflows

**Adding a new ETF to the portfolio:**
1. `python -m tools.optimize <TICKER>` — find optimal MA params
2. Update `DEFAULT_PORTFOLIO` in `tools/portfolio.py` with `(weight, ma_fast, ma_slow)`
3. `python -m tools.portfolio` — verify results

**Checking if the current signal regime changed:**
```bash
python -m tools.signal SPMO
```

**Running the held-out test after a full year of OOS data:**
```bash
python -m tools.optimize --final SPMO
```
Only run this once per year — it consumes the holdout period.
