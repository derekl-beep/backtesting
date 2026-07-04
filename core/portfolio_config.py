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

# Validated signal params for tickers researched but NOT in the live margin portfolio --
# e.g. rejected for margin on drawdown grounds but used as a call-options overlay
# underlying (SMH), or validated with real alpha but too correlated to SPMO to add
# (MTUM, XLK). Single source of truth so tools don't each re-derive or hardcode these;
# see research/etf_candidates.md for the backing walk-forward runs and rejection/acceptance
# reasoning.
CANDIDATE_SIGNALS = {
    "SMH": dict(ma_fast=50, ma_slow=100),   # tools.optimize SMH, pre-2022 folds; options overlay only, not margin
    "MTUM": dict(ma_fast=30, ma_slow=50),   # tools.optimize MTUM, 2026-07-03 -- rejected for portfolio (too correlated to SPMO)
    "XLK":  dict(ma_fast=10, ma_slow=100),  # tools.optimize XLK, 2026-07-03 -- rejected for portfolio (too correlated to SPMO)
}

# Fallback for tickers with no known params at all (e.g. first-look screener runs)
DEFAULT_SIGNAL = dict(ma_fast=50, ma_slow=100)


def resolve_signal_params(ticker: str) -> dict:
    """
    Best-known MA params for `ticker`, checked in order: live portfolio,
    researched candidates, generic fallback. Single resolution path so every
    tool/script sees the same answer instead of each hardcoding its own
    PORTFOLIO.get(ticker, DEFAULT_SIGNAL) fallback.
    """
    if ticker in PORTFOLIO:
        return PORTFOLIO[ticker]
    if ticker in CANDIDATE_SIGNALS:
        return CANDIDATE_SIGNALS[ticker]
    return DEFAULT_SIGNAL


MACD_PARAMS = (12, 26, 9)
