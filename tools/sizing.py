"""
Risk-adjusted sizing analysis for the SPMO options strategy.

Shows how Calmar ratio (CAGR / |MaxDD|) and Sharpe respond to the options
budget fraction, helping you pick a budget that matches your risk tolerance.

Calmar is the primary metric here — it captures both the return objective
and the drawdown constraint (margin calls, psychological tolerance). Sharpe
alone doesn't capture tail risk; MaxDD alone doesn't capture frequency.

Three sizing tiers are derived from the sweep:
  Conservative  — maximize Sharpe (best risk-adjusted per unit of vol)
  Moderate      — Calmar ≥ 1.5  (good return for drawdown taken)
  Aggressive    — maximize CAGR  (highest return, accepting larger drawdown)

Also shows a Kelly cross-check on the options layer. Important caveat:
Kelly is unreliable with <30 regime observations. The estimates here are
directional only — treat them as a sanity check, not a prescription.

Usage:
  python -m tools.sizing
  python -m tools.sizing --delta 0.30   # OTM calls
  python -m tools.sizing --capital 150000
"""

import sys
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.config import INITIAL_CAPITAL
from core.metrics import calc
from pathlib import Path
from tools.options_backtest import (
    CALL_TICKER, PORTFOLIO, ROLL_DTE, SIGNAL_TICKER, SWEEP_BUDGETS,
    _build_portfolio_equity, _fetch_all, _get_regimes, budget_sweep, run,
)
from signals import ma as sig_ma

CHART_DIR = Path(__file__).parent.parent / "charts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _margin_regime_returns(margin_equity: pd.Series, regimes: list) -> list[float]:
    """Per-regime return on the margin equity curve."""
    rets = []
    for start, end in regimes:
        try:
            i0 = margin_equity.index.searchsorted(pd.Timestamp(start))
            i1 = margin_equity.index.searchsorted(pd.Timestamp(end))
            if i0 >= len(margin_equity) or i1 >= len(margin_equity):
                continue
            rets.append(margin_equity.iloc[i1] / margin_equity.iloc[i0] - 1)
        except Exception:
            continue
    return rets


def _regime_stats(returns: list[float]) -> dict:
    """Summary stats for a list of per-regime returns."""
    arr = np.array(returns)
    wins = (arr > 0).sum()
    losses = (arr <= 0).sum()
    win_returns = arr[arr > 0]
    loss_returns = arr[arr <= 0]
    mu = arr.mean()
    sigma = arr.std(ddof=1) if len(arr) > 1 else 0.0
    # Gaussian Kelly: f* = μ/σ² — gives optimal fraction of capital per regime
    kelly = mu / sigma**2 if sigma > 0 else float("inf")
    # Binary Kelly for comparison
    avg_win  = win_returns.mean()  if len(win_returns)  else 0.0
    avg_loss = abs(loss_returns.mean()) if len(loss_returns) else 1e-9
    b = avg_win / avg_loss
    p = wins / len(arr)
    bin_kelly = max(0.0, (p * b - (1 - p)) / b) if avg_loss > 0 else 1.0
    return {
        "n":          len(arr),
        "wins":       int(wins),
        "losses":     int(losses),
        "win_rate":   p,
        "mean":       mu,
        "std":        sigma,
        "best":       arr.max(),
        "worst":      arr.min(),
        "kelly":      kelly,          # Gaussian Kelly fraction of capital
        "half_kelly": kelly / 2,
        "bin_kelly":  bin_kelly,      # Binary Kelly fraction of "betting unit"
    }


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def analyze(target_delta: float = 0.50, capital: float = INITIAL_CAPITAL,
            roll_dte: int = ROLL_DTE):
    from core.data import fetch

    spmo, qqq, vix, signal = _fetch_all()
    regimes = _get_regimes(signal)

    # 1. margin-only equity + per-regime stats
    margin_eq = _build_portfolio_equity(capital)
    margin_m   = calc(margin_eq)
    margin_rets = _margin_regime_returns(margin_eq, regimes)
    margin_stats = _regime_stats(margin_rets)

    # 2. options layer per-regime stats (at 10% budget, scale-independent)
    opt_rows = run(target_delta=target_delta, budget_frac=0.10,
                   capital=capital, roll_dte=roll_dte)
    # per-regime return ON PREMIUM (RoP) is budget-independent
    rop_values = [r["return_on_premium"] for r in opt_rows]
    opt_stats  = _regime_stats(rop_values)
    # convert kelly from "fraction of options budget" to "fraction of total capital"
    # If per-regime capital return = b × RoP → optimal b = μ_RoP / σ_RoP²
    opt_kelly_capital   = opt_stats["mean"] / opt_stats["std"]**2 if opt_stats["std"] > 0 else float("inf")
    opt_half_kelly_cap  = opt_kelly_capital / 2

    # 3. sweep: Calmar + Sharpe at each budget level
    margin_eq_ref, sweep_rows = budget_sweep(
        target_delta=target_delta, capital=capital, roll_dte=roll_dte,
    )
    for r in sweep_rows:
        r["calmar"] = r["cagr"] / abs(r["max_dd"]) if r["max_dd"] < 0 else float("inf")

    # 4. identify sizing tiers
    max_sharpe_row  = max(sweep_rows, key=lambda r: r["sharpe"])
    max_calmar_row  = max(sweep_rows, key=lambda r: r["calmar"])
    max_cagr_row    = max(sweep_rows, key=lambda r: r["cagr"])
    # Moderate: first budget where Calmar ≥ 1.5, else best Calmar available
    calmar_targets = [r for r in sweep_rows if r["calmar"] >= 1.5]
    moderate_row   = min(calmar_targets, key=lambda r: r["budget_frac"]) if calmar_targets else max_calmar_row
    moderate_desc  = "Calmar ≥ 1.5" if calmar_targets else f"max Calmar ({max_calmar_row['calmar']:.2f})"

    return {
        "capital":         capital,
        "target_delta":    target_delta,
        "regimes":         regimes,
        "margin_equity":   margin_eq,
        "margin_metrics":  margin_m,
        "margin_stats":    margin_stats,
        "opt_stats":       opt_stats,
        "opt_kelly_cap":   opt_kelly_capital,
        "opt_half_kelly_cap": opt_half_kelly_cap,
        "sweep":           sweep_rows,
        "tiers": {
            "conservative": (max_sharpe_row,  "best Sharpe"),
            "moderate":     (moderate_row,     moderate_desc),
            "aggressive":   (max_cagr_row,     "max CAGR"),
        },
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_analysis(res: dict):
    capital      = res["capital"]
    delta        = res["target_delta"]
    m_m          = res["margin_metrics"]
    m_s          = res["margin_stats"]
    o_s          = res["opt_stats"]
    sweep        = res["sweep"]
    tiers        = {k: v[0] for k, v in res["tiers"].items()}
    tier_descs   = {k: v[1] for k, v in res["tiers"].items()}

    cfg = PORTFOLIO[SIGNAL_TICKER]
    print(f"\n{'='*72}")
    print(f"  Risk-adjusted sizing analysis")
    print(f"  Signal: SPMO MA{cfg['ma_fast']}/{cfg['ma_slow']}  |  "
          f"QQQ Δ{delta:.2f} calls  |  capital: ${capital:,.0f}")
    print(f"{'='*72}")

    # ── Strategy metrics (across the full period) ──────────────────────────
    print(f"\n  ┌─ Strategy metrics (full period) {'─'*37}┐")
    hdr = f"  {'':30} {'Margin only':>12} {'Combined 3%':>12} {'Combined 5%':>12}"
    print(hdr)
    print(f"  {'─'*70}")

    row_3pct = next((r for r in sweep if r["budget_frac"] == 0.03), None)
    row_5pct = next((r for r in sweep if r["budget_frac"] == 0.05), None)

    def _fmt(val, fmt):
        return format(val, fmt) if val is not None else "—"

    metrics = [
        ("CAGR",        "cagr",    ".1%"),
        ("Sharpe",      "sharpe",  ".2f"),
        ("Max drawdown","max_dd",  ".1%"),
        ("Calmar",      "calmar",  ".2f"),
    ]
    for label, key, fmt in metrics:
        m_val  = m_m.get(key, None) if key != "calmar" else (m_m["cagr"] / abs(m_m["max_dd"]))
        r3_val = row_3pct[key] if row_3pct else None
        r5_val = row_5pct[key] if row_5pct else None
        print(f"  {label:<30} {_fmt(m_val, fmt):>12} "
              f"{_fmt(r3_val, fmt):>12} {_fmt(r5_val, fmt):>12}")

    print(f"  {'─'*70}")
    print(f"  {'Calmar = CAGR / |MaxDD| — higher is better risk-adjusted return':^70}")

    # ── Per-layer regime statistics ────────────────────────────────────────
    print(f"\n  ┌─ Per-regime outcomes ({m_s['n']} SPMO bull regimes) {'─'*20}┐")
    print(f"\n  {'':30} {'Margin layer':>14} {'Options layer (RoP)':>20}")
    print(f"  {'─'*66}")
    print(f"  {'Win rate':30} {m_s['win_rate']:>14.0%} {o_s['win_rate']:>20.0%}")
    print(f"  {'Mean return':30} {m_s['mean']:>+14.1%} {o_s['mean']:>+20.1%}")
    print(f"  {'Std dev':30} {m_s['std']:>14.1%} {o_s['std']:>20.1%}")
    print(f"  {'Best regime':30} {m_s['best']:>+14.1%} {o_s['best']:>+20.1%}")
    print(f"  {'Worst regime':30} {m_s['worst']:>+14.1%} {o_s['worst']:>+20.1%}")

    print(f"\n  Note: Margin returns are capital returns per regime.")
    print(f"        Options RoP is return on premium paid (budget-independent).")
    print(f"        To convert options RoP to capital return: capital_ret = budget% × RoP.")

    # ── Kelly cross-check ──────────────────────────────────────────────────
    print(f"\n  ┌─ Kelly cross-check (options layer) {'─'*33}┐")
    print(f"\n  Gaussian Kelly on total capital:")
    ok = res["opt_kelly_cap"]
    print(f"    Full Kelly budget fraction:   {min(ok, 9.99):.1%}"
          + ("  (uncapped theoretical max)" if ok > 1.0 else ""))
    print(f"    Half-Kelly (practical):       {min(ok/2, 9.99):.1%}")

    print(f"\n  ⚠  Kelly warning: with only {o_s['n']} regimes and {o_s['losses']} loss "
          f"observations, the Kelly estimate")
    print(f"     is statistically unreliable. High win rate + small losses → Kelly")
    print(f"     suggests large allocations. Use Calmar/Sharpe targets instead.")

    if o_s["losses"] == 0:
        print(f"\n     All {o_s['n']} regimes profitable — theoretical Kelly is infinite.")
        print(f"     Assume 1/5 future regimes lose 30% of premium → Kelly ≈ 12–18%.")
    print(f"\n  Practical guidance: start at Conservative, scale up after 3+ live regimes.")

    # ── Calmar / Sharpe sweep ──────────────────────────────────────────────
    print(f"\n  ┌─ Calmar + Sharpe as options budget scales {'─'*27}┐")
    margin_calmar = m_m["cagr"] / abs(m_m["max_dd"])
    print(f"\n  Baseline (margin only): CAGR {m_m['cagr']:.1%}, "
          f"Sharpe {m_m['sharpe']:.2f}, Calmar {margin_calmar:.2f}, MaxDD {m_m['max_dd']:.1%}")

    print(f"\n  {'Budget':>7}  {'CAGR':>7}  {'Sharpe':>7}  {'Calmar':>7}  "
          f"{'MaxDD':>7}  {'vs margin Calmar':>17}")
    print(f"  {'─'*62}")
    for r in sweep:
        tier_tag = ""
        if r is tiers["aggressive"] and r is not tiers["moderate"] and r is not tiers["conservative"]:
            tier_tag = f"  ← Aggressive ({tier_descs['aggressive']})"
        if r is tiers["moderate"] and r is not tiers["conservative"]:
            tier_tag = f"  ← Moderate ({tier_descs['moderate']})"
        if r is tiers["conservative"]:
            tier_tag = f"  ← Conservative ({tier_descs['conservative']})"
        calmar_delta = r["calmar"] - margin_calmar
        print(f"  {r['budget_frac']:>6.0%}  {r['cagr']:>7.1%}  {r['sharpe']:>7.2f}  "
              f"{r['calmar']:>7.2f}  {r['max_dd']:>7.1%}  "
              f"{calmar_delta:>+17.2f}{tier_tag}")

    # ── Sizing recommendations ─────────────────────────────────────────────
    print(f"\n  ┌─ Sizing recommendations {'─'*45}┐")
    print(f"\n  {'Tier':15}  {'Budget':>7}  {'CAGR':>7}  {'Sharpe':>7}  {'Calmar':>7}  {'MaxDD':>8}")
    print(f"  {'─'*60}")
    tier_labels = [
        ("Conservative", "conservative"),
        ("Moderate",     "moderate"),
        ("Aggressive",   "aggressive"),
    ]
    for label, key in tier_labels:
        desc = tier_descs[key]
        r = tiers[key]
        print(f"  {label:<15}  {r['budget_frac']:>6.0%}  {r['cagr']:>7.1%}  "
              f"{r['sharpe']:>7.2f}  {r['calmar']:>7.2f}  {r['max_dd']:>8.1%}  "
              f"({desc})")

    t_cons = tiers["conservative"]
    t_mod  = tiers["moderate"]
    t_agg  = tiers["aggressive"]
    print(f"\n  At ${capital:,.0f} capital:")
    print(f"    Conservative  ${capital * t_cons['budget_frac']:,.0f}/regime options budget  "
          f"({t_cons['budget_frac']:.0%})")
    print(f"    Moderate      ${capital * t_mod['budget_frac']:,.0f}/regime options budget   "
          f"({t_mod['budget_frac']:.0%})")
    print(f"    Aggressive    ${capital * t_agg['budget_frac']:,.0f}/regime options budget  "
          f"({t_agg['budget_frac']:.0%})")


def _plot_analysis(res: dict):
    sweep  = res["sweep"]
    tiers  = {k: v[0] for k, v in res["tiers"].items()}
    m_m    = res["margin_metrics"]
    delta  = res["target_delta"]

    budgets = [r["budget_frac"] * 100 for r in sweep]
    calmar  = [r["calmar"]  for r in sweep]
    sharpe  = [r["sharpe"]  for r in sweep]
    cagr    = [r["cagr"] * 100 for r in sweep]
    maxdd   = [abs(r["max_dd"]) * 100 for r in sweep]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(f"Risk-adjusted sizing — QQQ Δ{delta:.2f} calls on SPMO signal",
                 fontsize=12)

    # Top-left: Calmar vs budget
    ax = axes[0, 0]
    ax.plot(budgets, calmar, "o-", color="green", lw=2, ms=5)
    ax.axhline(m_m["cagr"] / abs(m_m["max_dd"]), color="gray", linestyle="--",
               label="Margin-only Calmar")
    ax.axhline(1.5, color="orange", linestyle=":", lw=1.2, label="Calmar 1.5 target")
    for tier_key, color, label in [
        ("conservative", "steelblue", "Conservative"),
        ("moderate",     "orange",    "Moderate"),
        ("aggressive",   "crimson",   "Aggressive"),
    ]:
        r = tiers[tier_key]
        ax.axvline(r["budget_frac"] * 100, color=color, linestyle="--", lw=1.2, alpha=0.7,
                   label=label)
    ax.set_xlabel("Options budget (% of capital per regime)")
    ax.set_ylabel("Calmar ratio (CAGR / |MaxDD|)")
    ax.set_title("Calmar ratio vs budget fraction")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Top-right: Sharpe vs budget
    ax = axes[0, 1]
    ax.plot(budgets, sharpe, "o-", color="steelblue", lw=2, ms=5)
    ax.axhline(m_m["sharpe"], color="gray", linestyle="--", label="Margin-only Sharpe")
    for tier_key, color in [
        ("conservative", "steelblue"),
        ("moderate",     "orange"),
        ("aggressive",   "crimson"),
    ]:
        r = tiers[tier_key]
        ax.axvline(r["budget_frac"] * 100, color=color, linestyle="--", lw=1.2, alpha=0.7)
    ax.set_xlabel("Options budget (% of capital per regime)")
    ax.set_ylabel("Sharpe ratio")
    ax.set_title("Sharpe ratio vs budget fraction")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Bottom-left: CAGR vs budget
    ax = axes[1, 0]
    ax.plot(budgets, cagr, "o-", color="darkorange", lw=2, ms=5)
    ax.axhline(m_m["cagr"] * 100, color="gray", linestyle="--", label="Margin-only CAGR")
    for tier_key, color in [
        ("conservative", "steelblue"),
        ("moderate",     "orange"),
        ("aggressive",   "crimson"),
    ]:
        r = tiers[tier_key]
        ax.axvline(r["budget_frac"] * 100, color=color, linestyle="--", lw=1.2, alpha=0.7)
    ax.set_xlabel("Options budget (% of capital per regime)")
    ax.set_ylabel("CAGR (%)")
    ax.set_title("CAGR vs budget fraction")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # Bottom-right: MaxDD vs budget (inverted: smaller = better)
    ax = axes[1, 1]
    ax.plot(budgets, maxdd, "o-", color="crimson", lw=2, ms=5)
    ax.axhline(abs(m_m["max_dd"]) * 100, color="gray", linestyle="--",
               label="Margin-only MaxDD")
    for tier_key, color in [
        ("conservative", "steelblue"),
        ("moderate",     "orange"),
        ("aggressive",   "crimson"),
    ]:
        r = tiers[tier_key]
        ax.axvline(r["budget_frac"] * 100, color=color, linestyle="--", lw=1.2, alpha=0.7)
    ax.set_xlabel("Options budget (% of capital per regime)")
    ax.set_ylabel("|Max drawdown| (%, lower = better)")
    ax.set_title("Max drawdown vs budget fraction")
    ax.invert_yaxis()
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # tier legend in figure space
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color="steelblue", linestyle="--", label="Conservative"),
        Line2D([0], [0], color="orange",    linestyle="--", label="Moderate"),
        Line2D([0], [0], color="crimson",   linestyle="--", label="Aggressive"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9,
               frameon=True, bbox_to_anchor=(0.5, 0.0))

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"sizing_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args    = sys.argv[1:]
    capital = INITIAL_CAPITAL
    delta   = 0.50

    if "--capital" in args:
        idx     = args.index("--capital")
        capital = float(args[idx + 1])
        args    = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    if "--delta" in args:
        idx   = args.index("--delta")
        delta = float(args[idx + 1])
        args  = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    res = analyze(target_delta=delta, capital=capital)
    _print_analysis(res)
    _plot_analysis(res)
