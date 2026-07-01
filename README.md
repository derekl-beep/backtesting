# SPMO + GLD Portfolio Backtest

Momentum-based margin strategy backtested on a two-ETF portfolio:
**SPMO** (Invesco S&P 500 Momentum ETF, 80%) + **GLD** (SPDR Gold, 20%).

## Strategy

Each ETF runs its own independent MA crossover signal with 2x leverage when bullish:

| ETF | Weight | Signal | Validation |
|-----|--------|--------|------------|
| SPMO | 80% | MA10/200 | 5/8 OOS folds, avg +13.0% vs B&H |
| GLD  | 20% | MA20/100 | 5/8 OOS folds, avg +13.0% vs B&H |

- **Bullish**: hold at **2x leverage** using margin
- **Bearish**: hold at **1x** (no margin)
- Margin borrow cost deducted daily on the borrowed portion
- Margin call simulated: if equity ratio falls below 30%, position is force-reduced

GLD was selected via ETF screener (`tools/screen.py`) for its low correlation to SPMO (0.16) and strong strategy alpha. MA-only signals were chosen over MA+RSI+MACD combos — multi-signal increased fees 5x with no net benefit after costs.

### Validation

Walk-forward optimization (expanding window, 2016 anchor), tuned jointly at the
portfolio level via `tools/tune.py` — per-ticker optima proved fragile once
portfolio-level fee drag was accounted for (see `RESEARCH.md`):
- OOS folds: 2018–2025 — used to select MA params
- Final held-out test: 2025–present (touched once per year)

## Portfolio results (2016–2026-07, starting capital $10,000)

| | B&H 1x | B&H 2x | Strategy |
|---|---|---|---|
| Total return | 515.7% | 1453.5% | **1289.4%** |
| CAGR | 19.0% | 30.0% | **28.6%** |
| Sharpe ratio | 1.08 | 0.92 | **0.99** |
| Max drawdown | -26.4% | -49.3% | **-35.8%** |
| Margin calls | — | — | 0 |
| Total fees | — | — | $138 |

### Year-by-year

| Year | B&H 1x | B&H 2x | Strategy | vs 1x | vs 2x | MaxDD |
|---|---|---|---|---|---|---|
| 2016 | +7.0% | +7.7% | +8.7% | +1.7% | +1.0% | -7.9% |
| 2017 | +25.2% | +48.5% | +46.2% | +21.0% | -2.3% | -4.9% |
| 2018 | -1.6% | -11.4% | -1.3% | +0.3% | +10.1% | -27.7% |
| 2019 | +24.3% | +45.2% | +31.5% | +7.2% | -13.8% | -9.6% |
| 2020 | +26.5% | +35.1% | +44.9% | +18.4% | +9.8% | -35.8% |
| 2021 | +19.0% | +33.1% | +35.4% | +16.3% | +2.2% | -19.4% |
| 2022 | -9.0% | -25.3% | -20.7% | -11.8% | +4.5% | -32.7% |
| 2023 | +18.3% | +31.7% | +27.1% | +8.7% | -4.6% | -12.5% |
| 2024 | +44.3% | +94.0% | +94.8% | +50.5% | +0.9% | -23.5% |
| 2025 | +30.4% | +52.1% | +32.1% | +1.7% | -20.0% | -34.3% |
| 2026 | +24.5% | +48.6% | +37.9% | +13.3% | -10.7% | -19.6% |

The key insight from B&H 2x: the strategy gives up a little total return vs naive always-on leverage but with significantly lower max drawdown (-35.8% vs -49.3%) and higher Sharpe — the signal timing earns its keep in risk reduction, not raw returns.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install yfinance pandas matplotlib scipy pytest
```

Run the test suite (signal flips, simulator fee/borrow math, metrics, golden
end-to-end backtest, config invariants):

```bash
pytest
```

## Tools

### Daily signal check
```bash
python -m tools.signal SPMO GLD
python -m tools.signal SPMO --capital 50000
```
Shows per-ticker: MA values + state, current signal ON/OFF, days in regime, distance to flip, position sizing, last 5 signal flips.

### Backtest (single ETF)
```bash
python -m tools.backtest SPMO
python -m tools.backtest SPMO QQQ SPY
```
Lifetime summary + year-by-year. Saves chart to `backtest_results.png`.

### Portfolio backtest
```bash
python -m tools.portfolio
python -m tools.portfolio SPMO:0.8:50:100 GLD:0.2:30:50
```
Format: `TICKER:weight:ma_fast:ma_slow`. Runs each ETF independently, combines equity.
Shows B&H 1x, B&H 2x, and Strategy side-by-side. Saves chart to `portfolio_results.png`.

Weights + signal params (with optional RSI/MACD) live in `PORTFOLIO` in
`core/portfolio_config.py` — the single source of truth for backtests, live
signal checks, and `tools.tune --apply`.

### ETF screener
```bash
python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM EWJ NUKZ
```
Correlation matrix + per-ticker strategy stats (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD).
Use to find low-correlation candidates before adding to portfolio. Saves chart to `screen_results.png`.

### Portfolio tuning (joint optimization)
```bash
python -m tools.tune              # optimize all tickers jointly, show comparison
python -m tools.tune --apply      # same, but write changes if Sharpe improves
```
Portfolio-level walk-forward optimization across joint MA combos; `--apply` is
gated on Sharpe improvement and rewrites `core/portfolio_config.py`. Use this
(not per-ticker optimize) when retuning the whole portfolio.

### Walk-forward optimization (per ticker)
```bash
python -m tools.optimize SPMO
python -m tools.optimize --signals ma,rsi SPMO
python -m tools.optimize --signals ma,rsi,macd SPMO
python -m tools.optimize --final SPMO
```
Sweeps params across OOS folds (2018–2025). Run for each new ticker before adding to portfolio.

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

---

## Stock tools (feature/stock-backtesting branch)

Individual stocks use **momentum_cash** by default: 2x when MA_fast > MA_slow, 0x cash when bearish. Unlike the ETF strategy (1x hold when bearish), stocks exit completely.

### Daily rank
```bash
python -m tools.stock_rank                        # default 17-stock watchlist
python -m tools.stock_rank NVDA MSFT AAPL TSLA
```
Ranks by composite strength score (regime days + MA gap + RSI). Start here to find today's entry candidates.

### Live signal + sizing
```bash
python -m tools.stock_signal NVDA MSFT
python -m tools.stock_signal NVDA --capital 50000
```
Per-ticker: current signal (bull 2x / cash 0x), MA values, days in regime, distance to flip, position sizing, last 5 flips. Per-ticker strategy configs live in `STOCK_CONFIGS` at top of `tools/stock_signal.py`.

### Stock screener
```bash
python -m tools.stock_screen NVDA MSFT AAPL TSLA META
```
Runs momentum-cash (MA50/100 2x/0x) and mean-reversion (RSI band 1x/0x) side-by-side. Shows alpha for each strategy and recommends which to use. Correlation matrix included.

### Stock backtest
```bash
python -m tools.stock_backtest NVDA                       # momentum_cash vs mean_rev
python -m tools.stock_backtest NVDA MSFT AAPL
python -m tools.stock_backtest NVDA --strategy momentum_cash
python -m tools.stock_backtest NVDA --strategy mean_rev
python -m tools.stock_backtest NVDA --strategy compare    # momentum_cash vs ETF-style
```
Lifetime summary + year-by-year. Saves chart to `charts/backtest/`.

### Walk-forward optimization
```bash
python -m tools.stock_optimize NVDA                  # 2-tier: sweeps fast/slow pairs
python -m tools.stock_optimize --tier 3 NVDA         # 3-tier: sweeps fast/mid, slow=200
python -m tools.stock_optimize NVDA MSFT AAPL
```
Same expanding-window OOS structure as the ETF optimizer. Default (--tier 2) optimizes momentum_cash fast/slow MA params.

### Stock portfolio
```bash
python -m tools.stock_portfolio NVDA MSFT AAPL                   # equal weight
python -m tools.stock_portfolio NVDA:0.5 MSFT:0.3 AAPL:0.2      # specified weights
python -m tools.stock_portfolio NVDA MSFT AAPL --strategy mean_rev
```
Per-leg stats + portfolio aggregate vs B&H. Default strategy: momentum_cash.

---

## Configuration (`core/config.py`)

| Parameter | Value | Description |
|---|---|---|
| `INITIAL_CAPITAL` | 10,000 | Starting portfolio value ($) |
| `LEVERAGE` | 2.0 | Multiplier when bullish |
| `MARGIN_RATE` | 0.048 | Annual borrow rate (Futu HK USD) |
| `MAINTENANCE_MARGIN` | 0.30 | Margin call threshold |
| `FEE_PER_SHARE` | $0.0099 | Commission $0.0049 + platform $0.005 (Futu HK) |
| `FEE_MIN_PER_ORDER` | $1.99 | Min $0.99 commission + $1.00 platform (Futu HK) |
| `MAX_DRAWDOWN_LIMIT` | -50% | Hard constraint for optimization |
| `START` | 2016-01-01 | Historical data start date |

## Project structure

```
core/
  config.py             shared constants
  portfolio_config.py   live portfolio: weights + signal params (single source of truth)
  data.py           yfinance data fetching
  metrics.py        CAGR, Sharpe, max drawdown
  simulator.py      daily simulation engine (positions → equity)
signals/
  ma.py             MA crossover signal → 0/1
  ma_3tier.py       three-level MA signal → 0/1/2
  rsi.py            RSI threshold signal (momentum) → 0/1
  rsi_band.py       RSI band signal (mean-reversion, stateful latch) → 0/1
  macd.py           MACD crossover signal → 0/1
  combo.py          all_of / any_of / majority_of combinators
strategies/
  momentum.py       2x bull / 1x bear  (ETF-style)
  momentum_cash.py  2x bull / 0x cash  (stock default)
  momentum_3t.py    2x / 1x / 0x  (three-tier)
  mean_reversion.py 1x in-trade / 0x cash
tools/  (ETF — master branch)
  signal.py              live signal checker (params from core/portfolio_config.py)
  backtest.py            single-ETF backtest with chart
  portfolio.py           multi-ETF portfolio backtest with chart
  optimize.py            per-ticker walk-forward optimizer
  portfolio_optimize.py  joint portfolio-level optimizer
  tune.py                end-to-end pipeline: optimize → compare → apply
  screen.py              ETF screener: correlation + strategy stats
  compare.py             multi-strategy comparison
tools/  (stocks — feature/stock-backtesting branch)
  stock_rank.py     daily ranking by momentum strength
  stock_signal.py   live signal + position sizing (STOCK_CONFIGS at top)
  stock_screen.py   momentum-cash vs mean-rev alpha per ticker
  stock_backtest.py per-stock backtest with strategy selection
  stock_portfolio.py N-stock weighted portfolio backtest
  stock_optimize.py walk-forward MA optimizer (--tier 2 or --tier 3)
tests/              pytest suite: signals, simulator math, metrics, golden backtest, config invariants
```

## Roadmap

- **Mean-reversion for ETFs**: EWJ/EEM-type macro ETFs show near-zero alpha with MA crossover. A contrarian RSI or Bollinger Band strategy could capture their rotation moves, but requires different position sizing (no persistent 2x leverage) and independent validation. The stock `mean_reversion` module is a starting point but would need adaptation.
