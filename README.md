# SPMO Margin Strategy Backtest

Backtesting a momentum-based margin strategy on **SPMO** (Invesco S&P 500 Momentum ETF).

## Strategy

**MA50/100 crossover with 2x leverage**

- When MA50 > MA100 (bullish): hold SPMO at **2x leverage** using margin
- When MA50 < MA100 (bearish): hold SPMO at **1x** (no margin)
- Margin borrow cost deducted daily on the borrowed portion
- Margin call simulated: if equity ratio falls below 30%, position is force-reduced

### Validation

Validated via **rolling walk-forward optimization** (expanding window, 2020 anchor):
- OOS folds: 2022, 2023, 2024 — used to select MA50/100 as optimal params
- Final held-out test: 2025–present (touched once) — passed

MA50/100 was chosen over multi-signal combos (MA+RSI+MACD) because it had higher average out-of-sample CAGR (+12.5% vs B&H) with fewer params to overfit.

## Results (as of 2026-07, starting capital $10,000)

| | Buy & Hold | MA50/100 Strategy |
|---|---|---|
| Total return | 311.3% | **772.5%** |
| CAGR | 24.4% | **39.8%** |
| Sharpe ratio | 1.06 | **1.11** |
| Max drawdown | -30.9% | -37.7% |
| Margin calls | — | 0 |
| Total fees | — | $48 |

### Year-by-year

| Year | B&H | Strategy | vs B&H | Max DD | Margin days |
|---|---|---|---|---|---|
| 2020 | +27.1% | +50.9% | +23.8% | -30.9% | 141 |
| 2021 | +24.2% | +42.9% | +18.7% | -20.8% | 252 |
| 2022 | -10.4% | -13.5% | -3.1% | -32.3% | 83 |
| 2023 | +19.5% | +35.9% | +16.4% | -14.5% | 188 |
| 2024 | +47.2% | +99.7% | +52.5% | -25.4% | 252 |
| 2025 | +25.9% | +13.8% | -12.1% | -37.7% | 205 |
| 2026 | +35.6% | +61.5% | +25.9% | -14.7% | 58 |

Note: 2022 and 2025 the strategy underperformed B&H — the MA signal stayed bullish into early drops before flipping bearish.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install yfinance pandas matplotlib scipy
```

## Tools

### Daily signal check
```bash
python -m tools.signal SPMO
python -m tools.signal SPMO --capital 50000   # include position sizing
```
Shows: current MA values, signal ON/OFF, days in current regime, % price move to flip, position sizing, last 5 signal flips with prices.

### Backtest
```bash
python -m tools.backtest                  # SPMO, QQQ, SPY
python -m tools.backtest SPMO
```
Shows: lifetime summary + year-by-year breakdown. Saves chart to `backtest_results.png`.

### Walk-forward optimization
```bash
python -m tools.optimize SPMO                        # MA-only (default)
python -m tools.optimize --signals ma,rsi,macd SPMO  # multi-signal sweep
python -m tools.optimize --final SPMO                # final held-out test
```
Sweeps parameters for the selected signal set across rolling OOS folds. Each signal combination finds its own optimal params independently.

Available signals: `ma`, `rsi`, `macd` (comma-separated via `--signals`)

### Strategy comparison
```bash
python -m tools.compare SPMO
```
Side-by-side comparison of MA-only, MA+RSI+MACD majority, MA+RSI all, MA+MACD all, 0x cash, and SH hedge variants.

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
  signal.py       live signal checker
  backtest.py     full backtest with chart
  optimize.py     walk-forward parameter optimizer
  compare.py      multi-strategy comparison
```
