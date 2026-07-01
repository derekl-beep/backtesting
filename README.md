# SPMO + GLD Portfolio Backtest

Momentum-based margin strategy backtested on a two-ETF portfolio:
**SPMO** (Invesco S&P 500 Momentum ETF, 80%) + **GLD** (SPDR Gold, 20%).

## Strategy

Each ETF runs its own independent MA crossover signal with 2x leverage when bullish:

| ETF | Weight | Signal | Validation |
|-----|--------|--------|------------|
| SPMO | 80% | MA50/100 | 3/4 OOS folds, avg +12.5% vs B&H |
| GLD  | 20% | MA30/50  | 4/4 OOS folds, avg +17.7% vs B&H |

- **Bullish**: hold at **2x leverage** using margin
- **Bearish**: hold at **1x** (no margin)
- Margin borrow cost deducted daily on the borrowed portion
- Margin call simulated: if equity ratio falls below 30%, position is force-reduced

GLD was selected via ETF screener (`tools/screen.py`) for its low correlation to SPMO (0.18) and strong strategy alpha. MA-only signals were chosen over MA+RSI+MACD combos — multi-signal increased fees 5x with no net benefit after costs.

### Validation

Walk-forward optimization (expanding window, 2020 anchor):
- OOS folds: 2022–2025 — used to select MA params per ticker
- Final held-out test: 2025–present (touched once) — passed for SPMO

## Portfolio results (as of 2026-07, starting capital $10,000)

| | B&H 1x | B&H 2x | Strategy |
|---|---|---|---|
| Total return | 272.7% | 639.4% | **650.5%** |
| CAGR | 22.5% | 36.2% | **36.5%** |
| Sharpe ratio | 1.13 | 0.99 | **1.14** |
| Max drawdown | -25.6% | -46.8% | **-33.4%** |
| Margin calls | — | — | 0 |
| Total fees | — | — | $102 |

### Year-by-year

| Year | B&H 1x | B&H 2x | Strategy | vs 1x | vs 2x | MaxDD |
|---|---|---|---|---|---|---|
| 2020 | +26.4% | +35.5% | +48.7% | +22.3% | +13.3% | -25.4% |
| 2021 | +18.1% | +29.6% | +32.2% | +14.1% | +2.6% | -18.7% |
| 2022 | -8.7% | -24.4% | -11.6% | -2.9% | +12.8% | -29.8% |
| 2023 | +18.1% | +30.9% | +32.3% | +14.2% | +1.5% | -12.4% |
| 2024 | +43.8% | +91.8% | +91.7% | +47.9% | -0.1% | -23.1% |
| 2025 | +31.2% | +55.7% | +25.2% | -6.0% | -30.4% | -33.4% |
| 2026 | +25.1% | +48.3% | +42.3% | +17.2% | -6.0% | -16.4% |

The key insight from B&H 2x: the strategy matches naive always-on-leverage in total return but with significantly lower max drawdown (-33.4% vs -46.8%) and higher Sharpe — the signal timing earns its keep in risk reduction, not raw returns.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install yfinance pandas matplotlib scipy
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

Signal configs (with optional RSI/MACD) live in `DEFAULT_PORTFOLIO` in `tools/portfolio.py`.
**Keep in sync with `SIGNAL_CONFIGS` in `tools/signal.py`.**

### ETF screener
```bash
python -m tools.screen SPMO VGT VOO TLT GLD EEM IWM EWJ NUKZ
```
Correlation matrix + per-ticker strategy stats (B&H CAGR, strategy CAGR, alpha, Sharpe, MaxDD).
Use to find low-correlation candidates before adding to portfolio. Saves chart to `screen_results.png`.

### Walk-forward optimization
```bash
python -m tools.optimize SPMO
python -m tools.optimize --signals ma,rsi SPMO
python -m tools.optimize --signals ma,rsi,macd SPMO
python -m tools.optimize --final SPMO
```
Sweeps params across OOS folds (2022–2025). Run for each new ticker before adding to portfolio.

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Side-by-side of MA-only vs MA+RSI+MACD combos vs cash vs SH hedge.

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
| `START` | 2020-01-01 | Historical data start date |

## Project structure

```
core/
  config.py       shared constants
  data.py         yfinance data fetching
  metrics.py      CAGR, Sharpe, max drawdown
  simulator.py    daily simulation engine (positions → equity)
signals/
  ma.py           MA crossover signal
  rsi.py          RSI threshold signal
  macd.py         MACD crossover signal
  combo.py        all_of / any_of / majority_of combinators
strategies/
  momentum.py     signal → leverage positions
tools/
  signal.py       live signal checker (per-ticker configs)
  backtest.py     single-ETF backtest with chart
  portfolio.py    multi-ETF portfolio backtest with chart
  optimize.py     walk-forward parameter optimizer
  screen.py       ETF screener: correlation + strategy stats
  compare.py      multi-strategy comparison
```

## Roadmap

- **Mean-reversion strategy**: ETFs driven by macro/sector rotations (e.g. EWJ, EEM) don't trend well — MA crossover has near-zero alpha on them. A contrarian RSI or Bollinger Band strategy could capture these moves, but requires a separate signal framework, different position sizing, and independent validation. Would be a new strategy module alongside the existing momentum one.

- **Individual stock backtesting**: Extend the system to individual stocks within the same workspace, reusing `core/` and `signals/` infrastructure. Requires new modules: large-universe screener (`tools/stock_screen.py`), per-stock backtest with strategy selection (`tools/stock_backtest.py`), N-stock portfolio with dynamic allocation (`tools/stock_portfolio.py`), and additional strategy types (`strategies/mean_reversion.py`). The ETF workflow stays untouched; stocks share infrastructure but have separate entry points.
