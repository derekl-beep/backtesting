# SPMO Margin Strategy Backtest

Backtesting a momentum-based margin strategy on **SPMO** (Invesco S&P 500 Momentum ETF).

## Strategy

- **Bullish signal** (MA 50 > MA 200): hold SPMO at 2x leverage using margin
- **Bearish signal** (MA 50 < MA 200): hold SPMO at 1x (no margin)
- Margin borrow cost deducted daily on the borrowed half
- Margin call simulated: if equity ratio falls below 30% maintenance margin, position is force-reduced

### Optional: VIX volatility filter
When `VIX >= VIX_THRESHOLD` (default 25), margin is blocked even if the MA signal is bullish. Reduces drawdown at the cost of some CAGR.

## Results (as of 2026-07, starting capital $10,000)

| Strategy | CAGR | Sharpe | Max Drawdown | Total Fees |
|---|---|---|---|---|
| Buy & Hold SPMO | 21.2% | 1.03 | -30.9% | — |
| MA 50/200, 2x margin ✅ | **30.4%** | 0.89 | -56.0% | $57 |
| MA 20/50, 2x margin | 27.1% | 0.92 | -41.7% | $268 |
| MA 20/50 + VIX<25 filter | 25.7% | 0.93 | -35.6% | $468 |

**Chosen strategy: MA 50/200** — highest CAGR (30.4%), minimal trading fees ($57 over ~10 years), 85% of days in bullish/leveraged mode.

## Assumptions

- Initial capital: $10,000
- Leverage: 2x when bullish (buy $20,000 of SPMO, borrowing $10,000)
- Margin borrow rate: **4.8% annually** (Futu HK USD rate)
- Trade fees: **$0.0099/share** (commission $0.0049 + platform $0.005), min **$1.99/order** (Futu HK)
- Maintenance margin: 30% equity ratio (Futu HK requirement)
- Data: SPMO daily close via `yfinance`, SPMO inception ~2015

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install yfinance pandas matplotlib
python backtest.py
```

## Key Config (`backtest.py`)

| Parameter | Default | Description |
|---|---|---|
| `LEVERAGE` | 2.0 | Multiplier when bullish |
| `MARGIN_RATE` | 0.048 | Annual borrow rate |
| `MA_FAST` | 50 | Fast moving average window |
| `MA_SLOW` | 200 | Slow moving average window |
| `VIX_THRESHOLD` | 25 | Block margin above this VIX level |
| `MAINTENANCE_MARGIN` | 0.30 | Margin call threshold |

## Next Steps

- [ ] Stress-test with simulated crash scenarios (e.g., 2008-style drawdown)
- [ ] Explore dynamic leverage scaling based on MA signal strength
- [ ] Paper trade to validate live signal against backtest
