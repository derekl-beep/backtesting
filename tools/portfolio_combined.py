"""
Portfolio-level aggregation: margin legs (SPMO/GLD) + one or more call-options
overlays, combined into a single equity curve.

tools/options_backtest.py's --combined mode already does this for exactly one
overlay (the shipped SPMO signal -> QQQ calls). This generalizes it to N
overlays sharing the same capital base -- needed the moment more than one
options position runs at once (e.g. the shipped SPMO/QQQ overlay plus a new
SMH signal -> SMH calls overlay), since sizing each overlay off "3% of current
equity" only means the same thing if all overlays see the same, shared,
already-updated equity curve rather than being analyzed in isolation.

Regimes from every overlay are merged into one chronological queue and applied
to the equity curve in the order they actually start, so a later overlay's
budget sizing reflects any P&L already realized by an earlier one.

Usage:
  python -m tools.portfolio_combined                                # margin + shipped SPMO->QQQ overlay only
  python -m tools.portfolio_combined --add SMH:0.50:0.03             # + SMH signal -> SMH calls
  python -m tools.portfolio_combined --add SMH:0.50:0.03 --no-base   # SMH overlay only, no SPMO->QQQ
  python -m tools.portfolio_combined --add SMH:0.50:0.03 --capital 200000
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from core.metrics import calc
from tools.options_backtest import SIGNAL_TICKER, ROLL_DTE, _build_portfolio_equity, simulate_regime_with_rolls
from tools.options_common import overlay_inputs

CHART_DIR = Path(__file__).parent.parent / "charts" / "portfolio_combined"


def _overlay_spec(ticker, delta, budget, roll_dte):
    """Build an overlay spec dict for `ticker`'s own signal -> own calls, or
    the shipped SPMO -> QQQ cross-ticker overlay if ticker == SIGNAL_TICKER."""
    call_prices, iv_prices, regimes, name = overlay_inputs(ticker)
    return {
        "name":        name,
        "call_prices": call_prices,
        "iv_prices":   iv_prices,
        "regimes":     regimes,
        "delta":       delta,
        "budget":      budget,
        "roll_dte":    roll_dte,
    }


def _base_overlay_spec(delta, budget, roll_dte):
    return _overlay_spec(SIGNAL_TICKER, delta, budget, roll_dte)


def _extra_overlay_spec(ticker, delta, budget, roll_dte):
    return _overlay_spec(ticker, delta, budget, roll_dte)


def build_combined_equity(capital, overlay_specs):
    """
    Apply every overlay's regimes to one shared equity curve, in chronological
    order of regime start, so each overlay's dynamic budget sizing reflects
    prior overlays' realized P&L. Returns (margin_equity, combined_equity, events).
    """
    margin_equity = _build_portfolio_equity(capital)
    equity        = margin_equity.copy()

    queue = []
    for spec in overlay_specs:
        for start, end in spec["regimes"]:
            queue.append((pd.Timestamp(start), pd.Timestamp(end), spec))
    queue.sort(key=lambda x: x[0])

    events = []
    for start, end, spec in queue:
        entry_idx = equity.index.searchsorted(start)
        if entry_idx >= len(equity):
            continue
        current_equity = float(equity.iloc[entry_idx])

        sub_trades, agg = simulate_regime_with_rolls(
            start, end, spec["call_prices"], spec["iv_prices"],
            spec["delta"], spec["budget"], current_equity, 0.0, spec["roll_dte"])
        if not sub_trades:
            continue

        for leg in sub_trades:
            leg_entry_ts = pd.Timestamp(leg["entry_date"])
            leg_exit_ts  = pd.Timestamp(leg["exit_date"])
            if leg_entry_ts in equity.index:
                equity.loc[leg_entry_ts:] -= leg["premium_paid"]
            if leg_exit_ts in equity.index:
                equity.loc[leg_exit_ts:]  += leg["proceeds"]

        events.append({"overlay": spec["name"], "equity_at_entry": current_equity, **agg})

    return margin_equity, equity, events


def _print_report(margin_equity, combined_equity, events, capital, overlay_specs):
    m = calc(margin_equity)
    c = calc(combined_equity)

    print(f"\n{'='*72}")
    overlay_names = ", ".join(s["name"] for s in overlay_specs) or "(none)"
    print(f"  Combined portfolio: margin (SPMO/GLD) + {overlay_names}")
    print(f"{'='*72}")
    print(f"\n  {'':30} {'Margin only':>15} {'+ Overlays':>15}")
    print(f"  {'-'*60}")
    print(f"  {'Total return':30} {margin_equity.iloc[-1]/capital-1:>15.1%} "
          f"{combined_equity.iloc[-1]/capital-1:>15.1%}")
    print(f"  {'CAGR':30} {m['cagr']:>15.1%} {c['cagr']:>15.1%}")
    print(f"  {'Sharpe':30} {m['sharpe']:>15.2f} {c['sharpe']:>15.2f}")
    print(f"  {'Max drawdown':30} {m['max_dd']:>15.1%} {c['max_dd']:>15.1%}")

    print(f"\n  Per-overlay breakdown:")
    print(f"  {'Overlay':<12} {'Regimes':>8} {'Win rate':>9} {'Premium':>12} "
          f"{'Net P&L':>12} {'% of final equity':>18}")
    for spec in overlay_specs:
        evs = [e for e in events if e["overlay"] == spec["name"]]
        if not evs:
            print(f"  {spec['name']:<12} {'0':>8}")
            continue
        wins  = sum(1 for e in evs if e["total_pnl"] > 0)
        prem  = sum(e["total_premium"] for e in evs)
        pnl   = sum(e["total_pnl"] for e in evs)
        print(f"  {spec['name']:<12} {len(evs):>8} {f'{wins}/{len(evs)}':>9} "
              f"${prem:>10,.0f} {pnl:>+11,.0f}  {pnl/combined_equity.iloc[-1]:>+17.1%}")

    print(f"\n  CAGR lift from all overlays combined: {c['cagr'] - m['cagr']:+.1%}")


def _plot(margin_equity, combined_equity, overlay_specs):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(margin_equity.index, margin_equity.values, label="Margin only", lw=1.2)
    ax.plot(combined_equity.index, combined_equity.values,
            label="Margin + overlays", lw=1.2)
    ax.set_yscale("log")
    ax.set_title("Combined portfolio equity: margin + "
                 + ", ".join(s["name"] for s in overlay_specs))
    ax.legend()
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import date
    out = CHART_DIR / f"combined_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def run(capital=100_000, base_delta=0.50, base_budget=0.05, include_base=True,
        extra=None):
    overlay_specs = []
    if include_base:
        overlay_specs.append(_base_overlay_spec(base_delta, base_budget, ROLL_DTE))
    for ticker, delta, budget in (extra or []):
        overlay_specs.append(_extra_overlay_spec(ticker, delta, budget, ROLL_DTE))

    if not overlay_specs:
        print("No overlays selected (base disabled and no --add given) — nothing to combine.")
        return

    margin_equity, combined_equity, events = build_combined_equity(capital, overlay_specs)
    _print_report(margin_equity, combined_equity, events, capital, overlay_specs)
    chart_path = _plot(margin_equity, combined_equity, overlay_specs)
    print(f"\n  Chart saved to {chart_path}")


if __name__ == "__main__":
    args         = sys.argv[1:]
    capital      = 100_000
    base_delta   = 0.50
    base_budget  = 0.05
    include_base = True
    extra        = []

    i = 0
    while i < len(args):
        if args[i] == "--capital":
            capital = float(args[i + 1]); i += 2
        elif args[i] == "--delta":
            base_delta = float(args[i + 1]); i += 2
        elif args[i] == "--budget":
            base_budget = float(args[i + 1]); i += 2
        elif args[i] == "--no-base":
            include_base = False; i += 1
        elif args[i] == "--add":
            ticker, delta, budget = args[i + 1].split(":")
            extra.append((ticker.upper(), float(delta), float(budget)))
            i += 2
        else:
            i += 1

    run(capital=capital, base_delta=base_delta, base_budget=base_budget,
        include_base=include_base, extra=extra)
