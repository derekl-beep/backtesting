"""
Bear-regime put-selling overlay: sell monthly cash-secured OTM puts on the
call-overlay's underlying (QQQ for the shipped SPMO signal, or a ticker's own
underlying via --ticker) during every stretch the margin signal is bearish.

Research context (see research/strategy_experiments.md): unlike the covered-
call and bull-spread ideas tested alongside this one (both rejected -- they
cap the rare monster-move legs that drive this strategy's return), selling
puts during bear regimes doesn't touch the existing long position at all --
it's a standalone premium-harvesting overlay during periods the strategy is
already out of the market. Modestly positive in the original ad-hoc test;
this ships it as a real, tested tool.

Mechanics: each bear regime is split into ~30-day cycles. At the start of
each cycle, sell a target-delta (default -0.30, moderately OTM) put sized so
premium received is `budget_frac` of current cash. At cycle end, either the
put expires worthless (keep the premium) or is assigned (pay the intrinsic
value, i.e. strike minus spot) -- modeled as a cash-settled equivalent of a
real cash-secured put, same simplification the call overlay uses.

Usage:
  python -m tools.bear_put_overlay                    # SPMO signal -> QQQ puts
  python -m tools.bear_put_overlay --ticker SMH        # SMH signal -> SMH puts
  python -m tools.bear_put_overlay --delta -0.20 --budget 0.05
  python -m tools.bear_put_overlay --combined          # margin + bear-put overlay equity curve
"""

import sys

import pandas as pd

from tools.options_backtest import (
    RISK_FREE_RATE, SPREAD_COST, _build_portfolio_equity, _fetch_all,
    _get_bear_regimes, _print_yearly, bs_put, simulate_bear_regime_puts,
)

TARGET_DELTA = -0.30
BUDGET_FRAC  = 0.03


def run(ticker=None, target_delta=TARGET_DELTA, budget_frac=BUDGET_FRAC,
        capital=100_000, iv_shock=0.0):
    """Per-bear-regime aggregated results, one row per bear stretch."""
    _, underlying, iv, signal = _fetch_all(ticker)
    regimes = _get_bear_regimes(signal)

    results = []
    for start, end in regimes:
        _, agg = simulate_bear_regime_puts(start, end, underlying, iv,
                                           target_delta, budget_frac, capital,
                                           iv_shock)
        if agg:
            results.append(agg)
    return results


def combined_analysis(ticker=None, target_delta=TARGET_DELTA,
                      budget_frac=BUDGET_FRAC, capital=100_000, iv_shock=0.0):
    """
    Margin-only equity vs margin + bear-put overlay on the same capital base.
    Premium is received into the portfolio equity at each cycle start and the
    assignment payout (if any) is deducted at cycle end -- the mirror image
    of the call overlay's combined_analysis cash-flow direction.
    """
    _, underlying, iv, signal = _fetch_all(ticker)
    regimes = _get_bear_regimes(signal)

    margin_equity = _build_portfolio_equity(capital)
    overlay_equity = margin_equity.copy()
    events = []

    for start, end in regimes:
        entry_ts = pd.Timestamp(start)
        entry_idx = overlay_equity.index.searchsorted(entry_ts)
        if entry_idx >= len(overlay_equity):
            continue
        current_equity = float(overlay_equity.iloc[entry_idx])

        sub_trades, agg = simulate_bear_regime_puts(
            start, end, underlying, iv, target_delta, budget_frac,
            current_equity, iv_shock)
        if not sub_trades:
            continue

        for cyc in sub_trades:
            entry_cyc = pd.Timestamp(cyc["entry_date"])
            exit_cyc  = pd.Timestamp(cyc["exit_date"])
            if entry_cyc in overlay_equity.index:
                overlay_equity.loc[entry_cyc:] += cyc["premium_received"]
            if exit_cyc in overlay_equity.index:
                overlay_equity.loc[exit_cyc:] -= cyc["payout"]

        events.append({**agg, "equity_at_entry": current_equity})

    return margin_equity, overlay_equity, events


def _print_results(results, target_delta, budget_frac, ticker=None):
    label = ticker or "SPMO"
    print(f"\n{'='*78}")
    print(f"  {label} bear-regime put overlay -- Δ{target_delta:.2f}, "
          f"{budget_frac:.0%} of cash/cycle")
    print(f"{'='*78}")

    if not results:
        print("  No bear regimes with enough data to trade.")
        return

    print(f"\n  {'Entry':12} {'Exit':12} {'Cycles':>7} {'Assigned':>9} "
          f"{'Premium $':>11} {'P&L $':>11} {'RoP':>7}")
    print(f"  {'-'*72}")
    for r in results:
        print(f"  {r['entry_date']:12} {r['exit_date']:12} {r['n_cycles']:>7} "
              f"{r['n_assigned']:>9} {'$'+format(r['total_premium'], ',.0f'):>11} "
              f"{'$'+format(r['total_pnl'], '+,.0f'):>11} {r['return_on_premium']:>+6.0%}")

    total_prem = sum(r["total_premium"] for r in results)
    total_pnl  = sum(r["total_pnl"] for r in results)
    total_cycles = sum(r["n_cycles"] for r in results)
    total_assigned = sum(r["n_assigned"] for r in results)
    wins = sum(1 for r in results if r["total_pnl"] > 0)

    print(f"\n  Bear regimes traded: {len(results)}   Cycles: {total_cycles}   "
          f"Assigned: {total_assigned}/{total_cycles} "
          f"({total_assigned/total_cycles:.0%})" if total_cycles else "")
    print(f"  Regime win rate:     {wins}/{len(results)} = {wins/len(results):.0%}")
    print(f"  Total premium:       ${total_prem:,.0f}")
    print(f"  Net P&L:             ${total_pnl:+,.0f}  "
          f"({total_pnl/total_prem:+.0%} on premium)" if total_prem else "")


def _print_combined(margin_equity, overlay_equity, events, target_delta,
                    budget_frac, capital):
    from core.metrics import calc

    m = calc(margin_equity)
    o = calc(overlay_equity)

    print(f"\n{'='*70}")
    print(f"  Combined: Margin + bear-put overlay, Δ{target_delta:.2f}, "
          f"{budget_frac:.0%}/cycle")
    print(f"{'='*70}")
    print(f"\n  {'':30} {'Margin only':>15} {'+ Bear puts':>15}")
    print(f"  {'-'*60}")
    print(f"  {'CAGR':30} {m['cagr']:>15.1%} {o['cagr']:>15.1%}")
    print(f"  {'Sharpe':30} {m['sharpe']:>15.2f} {o['sharpe']:>15.2f}")
    print(f"  {'Max drawdown':30} {m['max_dd']:>15.1%} {o['max_dd']:>15.1%}")

    total_pnl = sum(e["total_pnl"] for e in events)
    total_prem = sum(e["total_premium"] for e in events)
    n_cycles = sum(e["n_cycles"] for e in events)
    n_assigned = sum(e["n_assigned"] for e in events)
    print(f"\n  Bear-put overlay summary:")
    print(f"    Bear regimes traded: {len(events)}   Cycles: {n_cycles}   "
          f"Assigned: {n_assigned}/{n_cycles} ({n_assigned/n_cycles:.0%})" if n_cycles else "")
    print(f"    Total premium:       ${total_prem:,.0f}")
    print(f"    Net P&L:             ${total_pnl:+,.0f}")
    print(f"    CAGR lift:           {o['cagr'] - m['cagr']:+.1%}")

    _print_yearly(overlay_equity, {"Margin only": margin_equity}, label="Combined")


def analyze(ticker=None, target_delta=TARGET_DELTA, budget_frac=BUDGET_FRAC,
           capital=100_000, show_combined=False):
    if show_combined:
        margin_eq, overlay_eq, events = combined_analysis(
            ticker=ticker, target_delta=target_delta, budget_frac=budget_frac,
            capital=capital)
        _print_combined(margin_eq, overlay_eq, events, target_delta,
                        budget_frac, capital)
    else:
        results = run(ticker=ticker, target_delta=target_delta,
                     budget_frac=budget_frac, capital=capital)
        _print_results(results, target_delta, budget_frac, ticker=ticker)


if __name__ == "__main__":
    args = sys.argv[1:]
    delta = TARGET_DELTA
    budget = BUDGET_FRAC
    capital = 100_000
    show_combined = "--combined" in args
    args = [a for a in args if a != "--combined"]

    if "--delta" in args:
        idx = args.index("--delta")
        delta = float(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--budget" in args:
        idx = args.index("--budget")
        budget = float(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
    if "--capital" in args:
        idx = args.index("--capital")
        capital = float(args[idx + 1])
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    ticker = None
    if "--ticker" in args:
        idx = args.index("--ticker")
        ticker = args[idx + 1].upper()
        args = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]

    analyze(ticker=ticker, target_delta=delta, budget_frac=budget,
           capital=capital, show_combined=show_combined)
