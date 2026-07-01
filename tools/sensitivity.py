"""
Parameter robustness analysis.

Two views per ticker:
  1. OOS sensitivity heatmap — every MA fast/slow combo evaluated directly on
     all walk-forward OOS folds (same grid and folds as tools.optimize).
     Current params on a warm plateau = trustworthy; a lone bright cell
     surrounded by cold = curve-fit.
  2. Rolling 1-year Sharpe — strategy vs B&H over the full history. A
     persistently shrinking gap is early warning of signal decay between
     annual holdout tests.

Usage:
  python -m tools.sensitivity              # all portfolio tickers
  python -m tools.sensitivity SPMO
"""

import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core import config
from core.data import fetch
from core.metrics import calc
from core.portfolio_config import PORTFOLIO, DEFAULT_SIGNAL
from core.simulator import run as simulate
from signals import ma as sig_ma
from strategies import momentum
from tools.optimize import (MA_FAST_WINDOWS, MA_SLOW_WINDOWS, TRAIN_START,
                            _bah, _build_folds, _run_params)

CHART_DIR      = Path(__file__).parent.parent / "charts" / "sensitivity"
ROLLING_WINDOW = 252


def _sweep_grid(prices, folds):
    """Avg OOS alpha + folds passed for every (fast, slow) cell."""
    alpha = pd.DataFrame(np.nan, index=MA_FAST_WINDOWS, columns=MA_SLOW_WINDOWS)
    passed = pd.DataFrame(np.nan, index=MA_FAST_WINDOWS, columns=MA_SLOW_WINDOWS)

    for fast in MA_FAST_WINDOWS:
        for slow in MA_SLOW_WINDOWS:
            if fast >= slow:
                continue
            alphas, n_pass = [], 0
            for _, oos, _ in folds:
                m = _run_params(oos, {"ma_fast": fast, "ma_slow": slow}, {"ma"})
                if m is None:
                    continue
                alphas.append(m["cagr"] - _bah(oos)["cagr"])
                if (m["max_dd"] >= config.MAX_DRAWDOWN_LIMIT and
                        m["margin_calls"] <= config.MAX_MARGIN_CALLS):
                    n_pass += 1
            if alphas:
                alpha.loc[fast, slow] = np.mean(alphas)
                passed.loc[fast, slow] = n_pass
    return alpha, passed


def _plot_heatmap(ticker, alpha, passed, n_folds, current):
    fig, ax = plt.subplots(figsize=(8, 6))
    data = alpha.values.astype(float) * 100
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto",
                   vmin=-np.nanmax(np.abs(data)), vmax=np.nanmax(np.abs(data)))

    ax.set_xticks(range(len(alpha.columns)), [f"MA{s}" for s in alpha.columns])
    ax.set_yticks(range(len(alpha.index)),  [f"MA{f}" for f in alpha.index])
    ax.set_xlabel("slow window")
    ax.set_ylabel("fast window")
    ax.set_title(f"{ticker} — avg OOS alpha vs B&H (% CAGR), {n_folds} folds\n"
                 f"cell note: folds passing constraints")

    for i, fast in enumerate(alpha.index):
        for j, slow in enumerate(alpha.columns):
            a = alpha.loc[fast, slow]
            if pd.isna(a):
                continue
            ax.text(j, i, f"{a*100:+.1f}\n{int(passed.loc[fast, slow])}/{n_folds}",
                    ha="center", va="center", fontsize=8)
            if (fast, slow) == current:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                           fill=False, edgecolor="blue", lw=2.5))

    fig.colorbar(im, ax=ax, label="avg OOS alpha (% CAGR)")
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    out = CHART_DIR / f"{ticker}_heatmap_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _rolling_sharpe(equity):
    ret = equity.pct_change().dropna()
    return (ret.rolling(ROLLING_WINDOW).mean() /
            ret.rolling(ROLLING_WINDOW).std() * np.sqrt(252)).dropna()


def _plot_rolling_sharpe(ticker, prices, cfg):
    sig    = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])
    pos    = momentum.positions(sig)
    result = simulate(prices, pos)

    strat_rs = _rolling_sharpe(result["equity"])
    bah_rs   = _rolling_sharpe(config.INITIAL_CAPITAL * prices / prices.iloc[0])

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(strat_rs.index, strat_rs.values,
            label=f"strategy MA{cfg['ma_fast']}/{cfg['ma_slow']}", lw=1.2)
    ax.plot(bah_rs.index, bah_rs.values, label="buy & hold", lw=1.2, alpha=0.7)
    ax.axhline(0, color="gray", lw=0.5)
    ax.set_title(f"{ticker} — rolling 1y Sharpe (strategy vs B&H)")
    ax.legend()
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    out = CHART_DIR / f"{ticker}_rolling_sharpe_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)

    gap = (strat_rs - bah_rs).dropna()
    return out, gap


def _neighbor_verdict(ticker, alpha, current):
    fast, slow = current
    if fast not in alpha.index or slow not in alpha.columns:
        print(f"  Current params MA{fast}/{slow} are outside the sweep grid.")
        return

    fi, si = list(alpha.index).index(fast), list(alpha.columns).index(slow)
    center = alpha.loc[fast, slow]
    neighbors = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == dj == 0:
                continue
            ni, nj = fi + di, si + dj
            if 0 <= ni < len(alpha.index) and 0 <= nj < len(alpha.columns):
                v = alpha.iloc[ni, nj]
                if not pd.isna(v):
                    neighbors.append((alpha.index[ni], alpha.columns[nj], v))

    print(f"\n  Current cell MA{fast}/{slow}: avg OOS alpha {center:+.1%}")
    print(f"  Neighbors:")
    for nf, ns, v in sorted(neighbors, key=lambda x: -x[2]):
        print(f"    MA{nf}/{ns:<4}  {v:+.1%}")

    positive = sum(1 for *_, v in neighbors if v > 0)
    if positive >= len(neighbors) / 2 and center > 0:
        print(f"  Verdict: PLATEAU — {positive}/{len(neighbors)} neighbors also "
              f"positive; params look robust.")
    else:
        print(f"  Verdict: ISOLATED — only {positive}/{len(neighbors)} neighbors "
              f"positive; treat current params with suspicion.")


def analyze(ticker: str):
    cfg    = PORTFOLIO.get(ticker, DEFAULT_SIGNAL)
    prices = fetch(ticker, start=TRAIN_START)
    folds  = _build_folds(prices, last_year=pd.Timestamp.now().year - 1)
    if not folds:
        print(f"{ticker}: not enough data.")
        return

    print(f"\n{'='*60}")
    print(f"  {ticker} — sensitivity around MA{cfg['ma_fast']}/{cfg['ma_slow']}")
    print(f"{'='*60}")

    alpha, passed = _sweep_grid(prices, folds)
    heatmap_path = _plot_heatmap(ticker, alpha, passed, len(folds),
                                 (cfg["ma_fast"], cfg["ma_slow"]))
    print(f"  Heatmap saved to {heatmap_path}")

    _neighbor_verdict(ticker, alpha, (cfg["ma_fast"], cfg["ma_slow"]))

    sharpe_path, gap = _plot_rolling_sharpe(ticker, prices, cfg)
    print(f"\n  Rolling Sharpe saved to {sharpe_path}")
    recent = gap.iloc[-ROLLING_WINDOW:].mean()
    full   = gap.mean()
    print(f"  Sharpe gap (strategy - B&H): full history {full:+.2f}, "
          f"last year {recent:+.2f}"
          + ("  ⚠ decaying" if recent < full - 0.3 else ""))


if __name__ == "__main__":
    tickers = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
    for t in tickers or list(PORTFOLIO):
        analyze(t)
