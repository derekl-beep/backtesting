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

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Returns: side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

## Architecture

```
core/
  config.py         shared constants
  data.py           yfinance fetch (returns pd.Series of daily close)
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
  signal.py              live signal check (SIGNAL_CONFIGS at top — keep in sync with portfolio.py)
  backtest.py            single-ETF backtest + chart
  portfolio.py           multi-ETF portfolio backtest + chart (DEFAULT_PORTFOLIO at top)
  optimize.py            per-ticker walk-forward optimizer
  portfolio_optimize.py  joint portfolio-level optimizer (sweeps all ticker combos together)
  tune.py                end-to-end pipeline: optimize → compare → apply
  screen.py              ETF screener: correlation + strategy stats
  compare.py             multi-strategy comparison
tools/  (stocks — feature/stock-backtesting branch)
  stock_rank.py     daily ranking of watchlist by momentum strength (start here)
  stock_signal.py   live signal + position sizing per stock (STOCK_CONFIGS at top)
  stock_screen.py   momentum-cash vs mean-rev alpha per ticker
  stock_backtest.py per-stock backtest with strategy selection
  stock_portfolio.py N-stock weighted portfolio backtest
  stock_optimize.py walk-forward MA optimizer (--tier 2 default, --tier 3 for 3-tier)
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
3. Update `DEFAULT_PORTFOLIO` in `tools/portfolio.py` and `SIGNAL_CONFIGS` in `tools/signal.py`
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
