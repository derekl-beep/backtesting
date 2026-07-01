"""
Single source of truth for the live portfolio.

Weights + signal params validated via walk-forward optimization.
Consumed by tools/portfolio.py (backtests), tools/signal.py (live checks),
and rewritten in place by `python -m tools.tune --apply`.
"""

PORTFOLIO = {
    #            weight  ma_fast  ma_slow
    "SPMO": dict(weight=0.80, ma_fast=10, ma_slow=200),   # joint portfolio optimization 2026-07-01
    "GLD":  dict(weight=0.20, ma_fast=20, ma_slow=100),   # joint portfolio optimization 2026-07-01
}

# Fallback for tickers not in the portfolio (e.g. ad-hoc signal checks)
DEFAULT_SIGNAL = dict(ma_fast=50, ma_slow=100)

MACD_PARAMS = (12, 26, 9)
