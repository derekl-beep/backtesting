"""
Options-parameter robustness analysis — the options-overlay analog of tools/sensitivity.py.

Two views per ticker:
  1. Delta x budget heatmap — median return-on-premium across every historical regime,
     evaluated at every (target_delta, budget_frac) combo. Current params on a warm
     plateau = trustworthy; a lone bright cell surrounded by cold = the "5% budget"
     default was picked by eyeballing one full-history sweep, not validated to be robust.
  2. First-half vs second-half regime split — median RoP in the first half of history
     vs the second half, at the current params. A big drop is an early warning that the
     edge (found via a full-history sweep, unlike the MA signal's walk-forward OOS
     validation) may be decaying or was concentrated in a few early regimes.

Usage:
  python -m tools.options_sensitivity              # default: SPMO signal -> QQQ calls
  python -m tools.options_sensitivity GLD SMH
"""

import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tools.options_backtest import SIGNAL_TICKER, ROLL_DTE, simulate_regime_with_rolls
from tools.options_common import overlay_inputs

CHART_DIR = Path(__file__).parent.parent / "charts" / "options_sensitivity"
CAPITAL   = 100_000
DELTAS    = [0.30, 0.40, 0.50, 0.60, 0.70, 0.85]
BUDGETS   = [0.01, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]
CURRENT_DELTA  = 0.50
CURRENT_BUDGET = 0.05


def _regime_rop(regime, call_prices, iv_prices, target_delta, budget_frac):
    start, end = regime
    _, agg = simulate_regime_with_rolls(start, end, call_prices, iv_prices,
                                        target_delta, budget_frac, CAPITAL,
                                        iv_shock=0.0, roll_dte=ROLL_DTE)
    return agg["return_on_premium"] if agg else None


def _sweep_grid(regimes, call_prices, iv_prices):
    """Median RoP + win rate for every (delta, budget) cell."""
    median_rop = pd.DataFrame(np.nan, index=DELTAS, columns=BUDGETS)
    win_rate   = pd.DataFrame(np.nan, index=DELTAS, columns=BUDGETS)

    for delta in DELTAS:
        for budget in BUDGETS:
            rops = [r for reg in regimes
                    if (r := _regime_rop(reg, call_prices, iv_prices, delta, budget)) is not None]
            if rops:
                median_rop.loc[delta, budget] = np.median(rops)
                win_rate.loc[delta, budget]   = np.mean([r > 0 for r in rops])
    return median_rop, win_rate


def _plot_heatmap(ticker, median_rop, win_rate, n_regimes, current):
    fig, ax = plt.subplots(figsize=(9, 6))
    data = median_rop.values.astype(float) * 100
    vmax = np.nanmax(np.abs(data))
    im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)

    ax.set_xticks(range(len(median_rop.columns)), [f"{b:.0%}" for b in median_rop.columns])
    ax.set_yticks(range(len(median_rop.index)), [f"Δ{d:.2f}" for d in median_rop.index])
    ax.set_xlabel("budget fraction")
    ax.set_ylabel("target delta")
    ax.set_title(f"{ticker} — median RoP (%) across {n_regimes} regimes\n"
                 f"cell note: win rate")

    for i, delta in enumerate(median_rop.index):
        for j, budget in enumerate(median_rop.columns):
            v = median_rop.loc[delta, budget]
            if pd.isna(v):
                continue
            ax.text(j, i, f"{v*100:+.0f}\n{win_rate.loc[delta, budget]:.0%}",
                    ha="center", va="center", fontsize=8)
            if (delta, budget) == current:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1,
                                           fill=False, edgecolor="blue", lw=2.5))

    fig.colorbar(im, ax=ax, label="median RoP (%)")
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    out = CHART_DIR / f"{ticker}_heatmap_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def _neighbor_verdict(ticker, median_rop, current):
    delta, budget = current
    if delta not in median_rop.index or budget not in median_rop.columns:
        print(f"  Current params Δ{delta}/{budget:.0%} are outside the sweep grid.")
        return

    di, bi = list(median_rop.index).index(delta), list(median_rop.columns).index(budget)
    center = median_rop.loc[delta, budget]
    neighbors = []
    for ddi in (-1, 0, 1):
        for dbj in (-1, 0, 1):
            if ddi == dbj == 0:
                continue
            ni, nj = di + ddi, bi + dbj
            if 0 <= ni < len(median_rop.index) and 0 <= nj < len(median_rop.columns):
                v = median_rop.iloc[ni, nj]
                if not pd.isna(v):
                    neighbors.append((median_rop.index[ni], median_rop.columns[nj], v))

    print(f"\n  Current cell Δ{delta:.2f}/{budget:.0%}: median RoP {center:+.0%}")
    print(f"  Neighbors:")
    for nd, nb, v in sorted(neighbors, key=lambda x: -x[2]):
        print(f"    Δ{nd:.2f}/{nb:<5.0%}  {v:+.0%}")

    positive = sum(1 for *_, v in neighbors if v > 0)
    if positive >= len(neighbors) / 2 and center > 0:
        print(f"  Verdict: PLATEAU — {positive}/{len(neighbors)} neighbors also "
              f"positive; params look robust.")
    else:
        print(f"  Verdict: ISOLATED — only {positive}/{len(neighbors)} neighbors "
              f"positive; treat current params with suspicion.")


def _decay_check(regimes, call_prices, iv_prices, delta, budget):
    """First-half vs second-half regimes (chronological), same params."""
    if len(regimes) < 4:
        print(f"\n  Only {len(regimes)} regimes — too few for a first/second-half split.")
        return

    mid = len(regimes) // 2
    first_half, second_half = regimes[:mid], regimes[mid:]

    def _median(regs):
        rops = [r for reg in regs
                if (r := _regime_rop(reg, call_prices, iv_prices, delta, budget)) is not None]
        return np.median(rops) if rops else None

    m1, m2 = _median(first_half), _median(second_half)
    if m1 is None or m2 is None:
        print("\n  Not enough regimes with valid trades in one half to compare.")
        return

    print(f"\n  First-half vs second-half median RoP at Δ{delta:.2f}/{budget:.0%} "
          f"({len(first_half)} vs {len(second_half)} regimes):")
    print(f"    First half  : {m1:+.0%}")
    print(f"    Second half : {m2:+.0%}"
          + ("  ⚠ declining" if m2 < m1 - 0.30 else ""))


def analyze(ticker: str):
    call_prices, iv_prices, regimes, label = overlay_inputs(ticker)
    if len(regimes) < 3:
        print(f"\n{ticker}: only {len(regimes)} regimes — not enough to sweep.")
        return

    label = label.replace("→", " signal -> ") + " calls"
    print(f"\n{'='*60}")
    print(f"  {label} — sensitivity around Δ{CURRENT_DELTA:.2f}/{CURRENT_BUDGET:.0%}")
    print(f"{'='*60}")

    median_rop, win_rate = _sweep_grid(regimes, call_prices, iv_prices)
    heatmap_path = _plot_heatmap(ticker, median_rop, win_rate, len(regimes),
                                 (CURRENT_DELTA, CURRENT_BUDGET))
    print(f"  Heatmap saved to {heatmap_path}")

    _neighbor_verdict(ticker, median_rop, (CURRENT_DELTA, CURRENT_BUDGET))
    _decay_check(regimes, call_prices, iv_prices, CURRENT_DELTA, CURRENT_BUDGET)


if __name__ == "__main__":
    tickers = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
    for t in tickers or [SIGNAL_TICKER]:
        analyze(t)
