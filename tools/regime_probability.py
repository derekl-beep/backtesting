"""
Probabilistic regime signal: walk-forward logistic regression, replacing the
hard MA on/off flip with a continuous P(bull regime) confidence measure.

Every signal in this project is a hard binary flip (MA10 > MA200 -> 2x, else
1x) -- one day fully levered, the next day (if the MA crosses) not, which is
exactly the mechanism behind whipsaw stretches like the Feb 2022 7-day
regime. This fits a logistic regression on simple technical features (MA
gap %, RSI, MACD histogram) against forward-return direction, walk-forward
(expanding window, same discipline as tools.optimize) so there's no lookahead,
and compares scaling leverage continuously with confidence against the
existing hard threshold.

Usage:
  python -m tools.regime_probability              # all portfolio tickers
  python -m tools.regime_probability SPMO
  python -m tools.regime_probability SMH --horizon 21
"""

import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from core.data import fetch
from core.metrics import calc
from core.simulator import run as simulate
from core.portfolio_config import PORTFOLIO, resolve_signal_params
import signals.ma as sig_ma
from signals.rsi import _rsi
from strategies import momentum

HORIZON = 21          # forward-return label horizon (~1 trading month)
L2 = 0.1              # ridge penalty (regularizes slopes, not the intercept)
FIRST_TEST_YEAR = 2018
MIN_TRAIN_OBS = 300
LEVERAGE_QUANTUM = 0.25   # round continuous leverage to this granularity


def _features(prices: pd.Series, ma_fast: int, ma_slow: int) -> pd.DataFrame:
    ma_f = prices.rolling(ma_fast).mean()
    ma_s = prices.rolling(ma_slow).mean()
    gap = (ma_f - ma_s) / ma_s
    rsi = (_rsi(prices, 14) - 50) / 50
    ema_fast = prices.ewm(span=12, adjust=False).mean()
    ema_slow = prices.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_sig = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = (macd_line - macd_sig) / prices
    X = pd.concat([gap, rsi, macd_hist], axis=1)
    X.columns = ["ma_gap", "rsi", "macd_hist"]
    return X.dropna()


def _neg_log_likelihood(beta, Xb, y):
    p = np.clip(expit(Xb @ beta), 1e-9, 1 - 1e-9)
    ll = (y * np.log(p) + (1 - y) * np.log(1 - p)).sum()
    return -ll + L2 * np.sum(beta[1:] ** 2)


def fit_logistic(X: pd.DataFrame, y: pd.Series) -> np.ndarray:
    Xb = np.column_stack([np.ones(len(X)), X.values])
    result = minimize(_neg_log_likelihood, np.zeros(Xb.shape[1]), args=(Xb, y.values),
                      method="BFGS")
    return result.x


def predict(beta: np.ndarray, X: pd.DataFrame) -> pd.Series:
    Xb = np.column_stack([np.ones(len(X)), X.values])
    return pd.Series(expit(Xb @ beta), index=X.index)


def walk_forward_probabilities(ticker: str, horizon: int = HORIZON,
                               first_test_year: int = FIRST_TEST_YEAR):
    """
    Expanding-window walk-forward: fit on all data through year Y-1, predict
    OOS probabilities for year Y, roll forward. No lookahead -- the forward-
    return label needs `horizon` future days, so the last `horizon` rows of
    each training window (which have no valid label yet) are dropped.
    """
    prices = fetch(ticker)
    cfg = resolve_signal_params(ticker)
    X = _features(prices, cfg["ma_fast"], cfg["ma_slow"])
    fwd_ret = prices.shift(-horizon) / prices - 1
    y_full = (fwd_ret > 0).astype(int)

    current_year = pd.Timestamp.now().year
    fold_info = []
    all_probs = []
    for test_year in range(first_test_year, current_year):
        train_X = X[X.index.year <= test_year - 1].iloc[:-horizon]
        test_X = X[X.index.year == test_year]
        if len(train_X) < MIN_TRAIN_OBS or test_X.empty:
            continue
        train_y = y_full.reindex(train_X.index)
        beta = fit_logistic(train_X, train_y)
        probs = predict(beta, test_X)
        all_probs.append(probs)

        train_pred = (predict(beta, train_X) > 0.5).astype(int)
        acc = float((train_pred == train_y).mean())
        fold_info.append({"year": test_year, "n_train": len(train_X),
                          "in_sample_acc": acc, "beta": beta})

    probs_series = pd.concat(all_probs) if all_probs else pd.Series(dtype=float)
    return probs_series, fold_info, cfg


def compare_strategies(ticker: str, horizon: int = HORIZON):
    prices = fetch(ticker)
    probs, fold_info, cfg = walk_forward_probabilities(ticker, horizon=horizon)
    if probs.empty:
        return None

    idx = probs.index
    hard_signal = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"]).reindex(idx)
    hard_pos = momentum.positions(hard_signal)
    hard_result = simulate(prices.reindex(idx), hard_pos)
    hard_m = calc(hard_result["equity"])

    quantized_leverage = ((1.0 + probs) / LEVERAGE_QUANTUM).round() * LEVERAGE_QUANTUM
    quantized_leverage = quantized_leverage.clip(1.0, 2.0)
    soft_result = simulate(prices.reindex(idx), quantized_leverage)
    soft_m = calc(soft_result["equity"])

    return {
        "ticker": ticker, "idx": idx, "probs": probs, "fold_info": fold_info,
        "hard_metrics": hard_m, "hard_result": hard_result, "hard_pos": hard_pos,
        "soft_metrics": soft_m, "soft_result": soft_result, "soft_leverage": quantized_leverage,
    }


def analyze(ticker: str, horizon: int = HORIZON):
    r = compare_strategies(ticker, horizon=horizon)
    if r is None:
        print(f"\n{ticker}: not enough data for a walk-forward fit.")
        return

    probs = r["probs"]
    print(f"\n{'='*74}")
    print(f"  {ticker} — probabilistic regime signal (walk-forward logistic regression)")
    print(f"{'='*74}")
    print(f"  Features: MA gap %, RSI(14), MACD histogram  |  "
          f"target: {horizon}-day forward return > 0")
    print(f"  In-sample fit accuracy by fold: " +
          ", ".join(f"{f['year']}={f['in_sample_acc']:.0%}" for f in r["fold_info"]))
    print(f"  OOS probability distribution: mean {probs.mean():.2f}, std {probs.std():.2f}, "
          f"range [{probs.min():.2f}, {probs.max():.2f}]")
    if probs.std() < 0.10:
        print(f"  ⚠ narrow probability range — these features have limited discriminating")
        print(f"    power for this ticker at this horizon (consistent with tools.significance's")
        print(f"    finding that this ticker's timing isn't clearly better than random).")

    hm, sm = r["hard_metrics"], r["soft_metrics"]
    hard_changes = int((r["hard_pos"].diff() != 0).sum())
    soft_changes = int((r["soft_leverage"].diff() != 0).sum())
    print(f"\n  {'':22} {'Hard (2x/1x flip)':>20} {'Continuous (1-2x)':>20}")
    print(f"  {'-'*64}")
    print(f"  {'CAGR':22} {hm['cagr']:>20.1%} {sm['cagr']:>20.1%}")
    print(f"  {'Sharpe':22} {hm['sharpe']:>20.2f} {sm['sharpe']:>20.2f}")
    print(f"  {'Max drawdown':22} {hm['max_dd']:>20.1%} {sm['max_dd']:>20.1%}")
    print(f"  {'Total fees':22} {'$'+format(r['hard_result']['total_fees'],',.0f'):>20} "
          f"{'$'+format(r['soft_result']['total_fees'],',.0f'):>20}")
    print(f"  {'Leverage changes':22} {hard_changes:>20} {soft_changes:>20}")

    verdict = "IMPROVES on" if (sm["sharpe"] > hm["sharpe"] and sm["max_dd"] > hm["max_dd"]) else "does NOT improve on"
    print(f"\n  Verdict: continuous confidence-scaling {verdict} the hard threshold "
          f"on this ticker/period.")


if __name__ == "__main__":
    args = sys.argv[1:]
    horizon = HORIZON
    if "--horizon" in args:
        idx = args.index("--horizon")
        horizon = int(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    tickers = [a.upper() for a in args if not a.startswith("--")] or list(PORTFOLIO)
    for t in tickers:
        analyze(t, horizon=horizon)
