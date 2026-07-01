"""Live portfolio config invariants.

The daily cloud signal check reads tools/signal.py while backtests read
tools/portfolio.py — these tests guarantee both always see the same params.
"""

import pytest


def test_signal_and_portfolio_params_match():
    from tools.portfolio import DEFAULT_PORTFOLIO
    from tools.signal import SIGNAL_CONFIGS

    assert set(SIGNAL_CONFIGS) == set(DEFAULT_PORTFOLIO)
    for ticker, cfg in DEFAULT_PORTFOLIO.items():
        for key in ("ma_fast", "ma_slow", "rsi", "macd"):
            assert SIGNAL_CONFIGS[ticker].get(key) == cfg.get(key), (
                f"{ticker}.{key} differs between signal.py and portfolio.py")


def test_weights_sum_to_one():
    from tools.portfolio import DEFAULT_PORTFOLIO
    total = sum(cfg["weight"] for cfg in DEFAULT_PORTFOLIO.values())
    assert total == pytest.approx(1.0)


def test_tune_apply_regex_matches_config_file():
    # tune.py --apply rewrites core/portfolio_config.py with this regex;
    # if the file format drifts, --apply would silently no-op.
    import pathlib
    import re

    from core.portfolio_config import PORTFOLIO

    text = (pathlib.Path(__file__).parent.parent / "core" / "portfolio_config.py").read_text()
    for ticker in PORTFOLIO:
        pattern = r'("' + ticker + r'":\s*dict\([^)]*ma_fast=)\d+([^)]*ma_slow=)\d+'
        assert re.search(pattern, text), f"tune --apply regex no longer matches {ticker}"


def test_ma_params_are_valid():
    from tools.portfolio import DEFAULT_PORTFOLIO
    for ticker, cfg in DEFAULT_PORTFOLIO.items():
        assert 0 < cfg["ma_fast"] < cfg["ma_slow"], f"{ticker}: fast must be < slow"
