"""
Options overlay backtest: buy QQQ calls at each SPMO bull regime start,
hold until the signal flips bearish, then close.

Strategy logic:
  - Signal source: SPMO MA10/200 (same as the margin leg)
  - Call vehicle:  QQQ (deeper market, tighter spreads, better signal transfer)
  - IV proxy:      ^VIX (downloadable daily history via yfinance)
  - Tenor:         fixed 6-month (180-day) calls, regardless of regime duration
  - Strike:        parameterized by delta — 0.85 (deep ITM), 0.50 (ATM), 0.30 (OTM)
  - Premium budget: fixed % of capital per regime entry (default 3%)

The Black-Scholes pricer uses VIX as σ at entry; at exit it uses a 21-day
realized vol of QQQ prices (regime is over — we know what vol realized).
This is optimistic vs buying real options (you face implied, not realized, at exit),
so the ±20% IV sensitivity run is the more conservative read.

Usage:
  python -m tools.options_backtest
  python -m tools.options_backtest --delta 0.50 --budget 0.03
  python -m tools.options_backtest --delta 0.85 --budget 0.05 --iv-shock 0.20
"""

import sys
import math
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core.data import fetch
from core.portfolio_config import PORTFOLIO

CHART_DIR = Path(__file__).parent.parent / "charts"
SIGNAL_TICKER  = "SPMO"
CALL_TICKER    = "QQQ"
IV_TICKER      = "^VIX"
TENOR_DAYS     = 180        # option tenor at entry (calendar days)
RISK_FREE_RATE = 0.045      # approximate T-bill rate
SPREAD_COST    = 0.003      # round-trip spread as fraction of option premium (0.3%)


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

def _d1(S, K, T, r, sigma):
    return (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))


def _d2(S, K, T, r, sigma):
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)


def _norm_cdf(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2


def bs_call(S, K, T, r, sigma):
    """Black-Scholes call price. T in years."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = _d1(S, K, T, r, sigma)
    d2 = _d2(S, K, T, r, sigma)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def bs_delta(S, K, T, r, sigma):
    """Call delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    return _norm_cdf(_d1(S, K, T, r, sigma))


def strike_for_delta(S, T, r, sigma, target_delta):
    """Binary search for the strike that gives the target delta."""
    lo, hi = S * 0.01, S * 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs_delta(S, mid, T, r, sigma) > target_delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Regime extraction
# ---------------------------------------------------------------------------

def _get_regimes(signal: pd.Series):
    """Return list of (start, end) dates for each bull regime (signal=1)."""
    diff   = signal.diff()
    starts = signal.index[diff == 1].tolist()
    ends   = signal.index[diff == -1].tolist()

    # if signal starts bullish, first start is the first index
    if signal.iloc[0] == 1:
        starts = [signal.index[0]] + starts

    regimes = []
    for start in starts:
        later_ends = [e for e in ends if e > start]
        end = later_ends[0] if later_ends else signal.index[-1]
        regimes.append((start, end))
    return regimes


# ---------------------------------------------------------------------------
# Single-regime option simulation
# ---------------------------------------------------------------------------

def _realized_vol(prices: pd.Series, ref_date: pd.Timestamp, window: int = 21) -> float:
    """Annualized realized vol of the last `window` days before ref_date."""
    sub = prices[prices.index <= ref_date].tail(window + 1)
    if len(sub) < 5:
        return 0.20
    ret = sub.pct_change().dropna()
    return float(ret.std() * math.sqrt(252))


def simulate_regime(entry_date, exit_date, qqq_prices, vix_prices,
                    target_delta, budget_frac, capital, iv_shock=0.0):
    """
    Simulate one call option trade over a single SPMO bull regime.
    Returns a dict with trade details, or None if not enough data.
    """
    # align to tradeable dates
    qqq_dates = qqq_prices.index
    entry_idx  = qqq_dates.searchsorted(entry_date)
    exit_idx   = qqq_dates.searchsorted(exit_date)
    if entry_idx >= len(qqq_dates) or exit_idx >= len(qqq_dates):
        return None
    entry_date = qqq_dates[entry_idx]
    exit_date  = qqq_dates[min(exit_idx, len(qqq_dates) - 1)]

    S_entry = float(qqq_prices.loc[entry_date])
    S_exit  = float(qqq_prices.loc[exit_date])
    T_entry = TENOR_DAYS / 365.0

    # IV at entry: VIX / 100 (VIX is in percent, annualized)
    vix_entry = vix_prices.reindex(qqq_prices.index, method="ffill").loc[entry_date]
    sigma_entry = float(vix_entry) / 100.0 * (1 + iv_shock)
    sigma_entry = max(sigma_entry, 0.05)

    # strike for target delta
    K = strike_for_delta(S_entry, T_entry, RISK_FREE_RATE, sigma_entry, target_delta)

    # call price at entry
    price_entry = bs_call(S_entry, K, T_entry, RISK_FREE_RATE, sigma_entry)
    if price_entry < 0.01:
        return None

    # --- exit pricing ---
    # remaining tenor
    calendar_days_held = (exit_date - entry_date).days
    T_exit = max((TENOR_DAYS - calendar_days_held) / 365.0, 0.0)

    # IV at exit: use 21-day realized vol (most favorable to strategy)
    sigma_exit = _realized_vol(qqq_prices, exit_date)

    price_exit = bs_call(S_exit, K, T_exit, RISK_FREE_RATE, sigma_exit)

    # trade economics
    premium_per_contract = price_entry * 100       # 1 contract = 100 shares
    budget = capital * budget_frac
    n_contracts = max(1, int(budget / premium_per_contract))
    premium_paid = n_contracts * premium_per_contract * (1 + SPREAD_COST)

    proceeds = n_contracts * price_exit * 100 * (1 - SPREAD_COST)
    pnl = proceeds - premium_paid
    return_on_premium = pnl / premium_paid
    qqq_return = S_exit / S_entry - 1

    actual_delta = bs_delta(S_entry, K, T_entry, RISK_FREE_RATE, sigma_entry)

    return {
        "entry_date":          str(entry_date.date()),
        "exit_date":           str(exit_date.date()),
        "days_held":           calendar_days_held,
        "qqq_S_entry":         round(S_entry, 2),
        "qqq_S_exit":          round(S_exit, 2),
        "qqq_return":          round(qqq_return, 4),
        "strike_K":            round(K, 2),
        "delta_at_entry":      round(actual_delta, 2),
        "vix_at_entry":        round(float(vix_entry), 1),
        "sigma_entry":         round(sigma_entry, 4),
        "sigma_exit":          round(sigma_exit, 4),
        "price_entry":         round(price_entry, 2),
        "price_exit":          round(price_exit, 2),
        "n_contracts":         n_contracts,
        "premium_paid":        round(premium_paid, 2),
        "proceeds":            round(proceeds, 2),
        "pnl":                 round(pnl, 2),
        "return_on_premium":   round(return_on_premium, 4),
        "capital_at_risk_pct": round(premium_paid / capital, 4),
    }


ROLL_DTE = 30   # roll when this many calendar days remain on the option


def simulate_regime_with_rolls(entry_date, exit_date, qqq_prices, vix_prices,
                                target_delta, budget_frac, capital, iv_shock=0.0,
                                roll_dte=ROLL_DTE):
    """
    Simulate a single bull regime using a rolling strategy.

    When a call reaches `roll_dte` days to expiry, close it and open a fresh
    ATM call with the same budget fraction applied to current cash. Repeat
    until the regime ends.

    Returns:
      sub_trades  — list of individual leg dicts (one per call bought)
      aggregate   — combined P&L/metrics across all legs
    """
    qqq_dates  = qqq_prices.index
    vix_ffill  = vix_prices.reindex(qqq_dates, method="ffill")
    roll_window = TENOR_DAYS - roll_dte   # hold each call this many calendar days

    sub_trades = []
    current_cash = float(capital)
    leg_entry = pd.Timestamp(entry_date)
    regime_end = pd.Timestamp(exit_date)

    while leg_entry < regime_end:
        # roll date: hold for roll_window calendar days, then roll
        roll_date  = leg_entry + pd.Timedelta(days=roll_window)
        leg_exit   = min(roll_date, regime_end)   # whichever comes first

        # snap to tradeable dates
        ei = qqq_dates.searchsorted(leg_entry)
        xi = qqq_dates.searchsorted(leg_exit)
        if ei >= len(qqq_dates):
            break
        ei = min(ei, len(qqq_dates) - 1)
        xi = min(xi, len(qqq_dates) - 1)
        leg_entry_ts = qqq_dates[ei]
        leg_exit_ts  = qqq_dates[xi]

        if leg_entry_ts >= leg_exit_ts:
            break

        S_entry = float(qqq_prices.iloc[ei])
        S_exit  = float(qqq_prices.iloc[xi])
        T_entry = TENOR_DAYS / 365.0

        vix_val     = float(vix_ffill.iloc[ei])
        sigma_entry = max(vix_val / 100.0 * (1 + iv_shock), 0.05)
        K = strike_for_delta(S_entry, T_entry, RISK_FREE_RATE, sigma_entry, target_delta)

        price_entry = bs_call(S_entry, K, T_entry, RISK_FREE_RATE, sigma_entry)
        if price_entry < 0.01:
            break

        # size to current cash
        budget   = current_cash * budget_frac
        n_contr  = max(1, int(budget / (price_entry * 100)))
        prem_paid = n_contr * price_entry * 100 * (1 + SPREAD_COST)

        # exit pricing
        days_held = (leg_exit_ts - leg_entry_ts).days
        T_exit    = max((TENOR_DAYS - days_held) / 365.0, 0.0)
        sigma_exit = _realized_vol(qqq_prices, leg_exit_ts)
        price_exit = bs_call(S_exit, K, T_exit, RISK_FREE_RATE, sigma_exit)
        proceeds   = n_contr * price_exit * 100 * (1 - SPREAD_COST)

        pnl = proceeds - prem_paid
        current_cash -= prem_paid
        current_cash += proceeds

        is_roll = leg_exit < regime_end

        sub_trades.append({
            "entry_date":        str(leg_entry_ts.date()),
            "exit_date":         str(leg_exit_ts.date()),
            "days_held":         days_held,
            "is_roll":           is_roll,
            "S_entry":           round(S_entry, 2),
            "S_exit":            round(S_exit, 2),
            "qqq_return":        round(S_exit / S_entry - 1, 4),
            "strike_K":          round(K, 2),
            "delta_at_entry":    round(bs_delta(S_entry, K, T_entry, RISK_FREE_RATE, sigma_entry), 2),
            "vix_at_entry":      round(vix_val, 1),
            "n_contracts":       n_contr,
            "premium_paid":      round(prem_paid, 2),
            "proceeds":          round(proceeds, 2),
            "pnl":               round(pnl, 2),
            "return_on_premium": round(pnl / prem_paid, 4),
        })

        leg_entry = leg_exit_ts + pd.Timedelta(days=1)

    if not sub_trades:
        return [], None

    total_prem = sum(t["premium_paid"] for t in sub_trades)
    total_pnl  = sum(t["pnl"]          for t in sub_trades)
    regime_qqq_ret = (
        float(qqq_prices.reindex([regime_end], method="ffill").iloc[0]) /
        float(qqq_prices.reindex([pd.Timestamp(entry_date)], method="ffill").iloc[0]) - 1
    )

    aggregate = {
        "entry_date":        str(pd.Timestamp(entry_date).date()),
        "exit_date":         str(regime_end.date()),
        "n_legs":            len(sub_trades),
        "total_premium":     round(total_prem, 2),
        "total_proceeds":    round(total_prem + total_pnl, 2),
        "total_pnl":         round(total_pnl, 2),
        "return_on_premium": round(total_pnl / total_prem, 4) if total_prem else 0,
        "regime_qqq_return": round(regime_qqq_ret, 4),
        "capital_start":     round(capital, 2),
        "capital_end":       round(current_cash, 2),
    }
    return sub_trades, aggregate


# ---------------------------------------------------------------------------
# Full backtest
# ---------------------------------------------------------------------------

def _fetch_all():
    """Fetch and return all shared price series (cached after first call)."""
    from signals import ma as sig_ma
    spmo = fetch(SIGNAL_TICKER)
    qqq  = fetch(CALL_TICKER)
    vix  = fetch(IV_TICKER)
    cfg  = PORTFOLIO[SIGNAL_TICKER]
    signal = sig_ma.signal(spmo, cfg["ma_fast"], cfg["ma_slow"])
    return spmo, qqq, vix, signal


def run(target_delta=0.50, budget_frac=0.03, capital=100_000, iv_shock=0.0,
        roll_dte=ROLL_DTE):
    spmo, qqq, vix, signal = _fetch_all()
    regimes = _get_regimes(signal)

    results = []
    for start, end in regimes:
        _, agg = simulate_regime_with_rolls(start, end, qqq, vix,
                                            target_delta, budget_frac, capital,
                                            iv_shock, roll_dte)
        if agg:
            # map aggregate keys to the legacy format callers expect
            results.append({
                "entry_date":        agg["entry_date"],
                "exit_date":         agg["exit_date"],
                "days_held":         (pd.Timestamp(agg["exit_date"]) -
                                      pd.Timestamp(agg["entry_date"])).days,
                "qqq_return":        agg["regime_qqq_return"],
                "vix_at_entry":      0,   # aggregate — not meaningful per-regime
                "strike_K":          0,
                "delta_at_entry":    target_delta,
                "premium_paid":      agg["total_premium"],
                "proceeds":          agg["total_proceeds"],
                "pnl":               agg["total_pnl"],
                "return_on_premium": agg["return_on_premium"],
                "n_legs":            agg["n_legs"],
            })

    return results


# ---------------------------------------------------------------------------
# Combined margin + options equity curve
# ---------------------------------------------------------------------------

def _build_portfolio_equity(capital: float) -> pd.Series:
    """
    Reconstruct the two-leg portfolio equity curve (SPMO 80% + GLD 20%, 2x
    when bullish, 1x when bearish) using the same simulator as tools/portfolio.
    Returns a daily equity Series starting at `capital`.
    """
    from core.simulator import run as simulate
    from signals import ma as sig_ma
    from strategies import momentum

    legs = []
    for ticker, cfg in PORTFOLIO.items():
        prices = fetch(ticker)
        leg_capital = capital * cfg["weight"]
        sig = sig_ma.signal(prices, cfg["ma_fast"], cfg["ma_slow"])
        pos = momentum.positions(sig)
        result = simulate(prices, pos, capital=leg_capital)
        legs.append(result["equity"])

    # align to common dates and sum
    combined = pd.concat(legs, axis=1).dropna()
    return combined.sum(axis=1)


def combined_analysis(target_delta=0.50, budget_frac=0.03, capital=100_000,
                      iv_shock=0.0, roll_dte=ROLL_DTE):
    """
    Show margin-only equity vs margin + ATM call overlay on the same capital base.
    The option premium is drawn from (and proceeds returned to) the portfolio equity.
    Rolls are injected as cash flows at each leg boundary within a regime.
    """
    spmo, qqq, vix, signal = _fetch_all()
    regimes = _get_regimes(signal)

    margin_equity = _build_portfolio_equity(capital)
    overlay_equity = margin_equity.copy()
    option_events = []

    for start, end in regimes:
        entry_ts  = pd.Timestamp(start)
        entry_idx = overlay_equity.index.searchsorted(entry_ts)
        if entry_idx >= len(overlay_equity):
            continue
        current_equity = float(overlay_equity.iloc[entry_idx])

        sub_trades, agg = simulate_regime_with_rolls(
            start, end, qqq, vix, target_delta, budget_frac,
            current_equity, iv_shock, roll_dte)
        if not sub_trades:
            continue

        # inject each leg's cash flows into the equity curve
        for leg in sub_trades:
            leg_entry_ts = pd.Timestamp(leg["entry_date"])
            leg_exit_ts  = pd.Timestamp(leg["exit_date"])
            if leg_entry_ts in overlay_equity.index:
                overlay_equity.loc[leg_entry_ts:] -= leg["premium_paid"]
            if leg_exit_ts in overlay_equity.index:
                overlay_equity.loc[leg_exit_ts:]  += leg["proceeds"]

        option_events.append({
            "entry":           agg["entry_date"],
            "exit":            agg["exit_date"],
            "n_legs":          agg["n_legs"],
            "prem":            agg["total_premium"],
            "proc":            agg["total_proceeds"],
            "pnl":             agg["total_pnl"],
            "rop":             agg["return_on_premium"],
            "equity_at_entry": current_equity,
        })

    return margin_equity, overlay_equity, option_events


def _print_combined(margin_equity, overlay_equity, option_events,
                    target_delta, budget_frac, capital):
    from core.metrics import calc

    m_metrics = calc(margin_equity)
    o_metrics = calc(overlay_equity)

    shock_val = (overlay_equity.iloc[-1] / capital - 1)
    margin_val = (margin_equity.iloc[-1] / capital - 1)

    print(f"\n{'='*70}")
    print(f"  Combined: Margin + QQQ Δ{target_delta:.2f} calls, {budget_frac:.0%}/regime")
    print(f"{'='*70}")
    print(f"\n  {'':30} {'Margin only':>15} {'+ Call overlay':>15}")
    print(f"  {'─'*60}")
    print(f"  {'Total return':30} {margin_val:>15.1%} {shock_val:>15.1%}")
    print(f"  {'CAGR':30} {m_metrics['cagr']:>15.1%} {o_metrics['cagr']:>15.1%}")
    print(f"  {'Sharpe':30} {m_metrics['sharpe']:>15.2f} {o_metrics['sharpe']:>15.2f}")
    print(f"  {'Max drawdown':30} {m_metrics['max_dd']:>15.1%} {o_metrics['max_dd']:>15.1%}")

    total_pnl = sum(e["pnl"] for e in option_events)
    total_prem = sum(e["prem"] for e in option_events)
    wins = sum(1 for e in option_events if e["pnl"] > 0)
    n = len(option_events)
    print(f"\n  Option overlay summary:")
    print(f"    Regimes traded:   {n}")
    print(f"    Win rate:         {wins}/{n} = {wins/n:.0%}")
    print(f"    Total premium:    ${total_prem:,.0f}  ({total_prem/capital:.1%} of capital)")
    print(f"    Net P&L from calls: ${total_pnl:+,.0f}  ({total_pnl/total_prem:+.0%} on premium)")
    print(f"    CAGR lift:        {o_metrics['cagr'] - m_metrics['cagr']:+.1%}")

    _print_yearly(overlay_equity,
                  {"Margin only": margin_equity},
                  label="Combined")


def _plot_combined(margin_equity, overlay_equity, target_delta, budget_frac):
    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                             gridspec_kw={"height_ratios": [3, 1]})

    ax = axes[0]
    ax.plot(margin_equity.index, margin_equity.values,
            label="Margin only (SPMO 80% + GLD 20%, 2×)", color="steelblue", lw=1.5)
    ax.plot(overlay_equity.index, overlay_equity.values,
            label=f"+ QQQ Δ{target_delta:.2f} calls ({budget_frac:.0%}/regime)",
            color="darkorange", lw=1.5)
    ax.set_ylabel("Portfolio value ($)")
    ax.set_title(f"Margin strategy vs margin + call overlay\n"
                 f"QQQ ATM (Δ{target_delta:.2f}), {budget_frac:.0%} budget per SPMO bull regime")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # bottom panel: daily difference (overlay advantage)
    ax2 = axes[1]
    diff = overlay_equity - margin_equity
    ax2.fill_between(diff.index, diff.values, 0,
                     where=diff > 0, color="green", alpha=0.4, label="overlay ahead")
    ax2.fill_between(diff.index, diff.values, 0,
                     where=diff < 0, color="red", alpha=0.4, label="overlay behind")
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_ylabel("Overlay advantage ($)")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_combined_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}")


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_results(results, target_delta, budget_frac, iv_shock):
    shock_str = f"  [IV shock: {iv_shock:+.0%}]" if iv_shock else ""
    cfg = PORTFOLIO[SIGNAL_TICKER]
    print(f"\n{'='*80}")
    print(f"  QQQ Call Backtest — Δ{target_delta:.2f} strike, "
          f"{budget_frac:.0%} budget/regime, roll at {ROLL_DTE} DTE{shock_str}")
    print(f"  Signal source: SPMO MA{cfg['ma_fast']}/{cfg['ma_slow']}")
    print(f"{'='*80}")

    # rolling results have n_legs; single-leg results don't
    has_legs = any(r.get("n_legs", 1) > 1 for r in results)

    if has_legs:
        col = "{:<12} {:<12} {:>5} {:>8} {:>6} {:>10} {:>9} {:>7}"
        header = col.format("Entry", "Exit", "Days", "QQQ ret", "Legs",
                            "Prem $", "P&L $", "RoP")
    else:
        col = "{:<12} {:<12} {:>5} {:>8} {:>7} {:>7} {:>8} {:>9} {:>7}"
        header = col.format("Entry", "Exit", "Days", "QQQ ret", "VIX",
                            "Strike", "Prem $", "P&L $", "RoP")

    print(f"\n  {header}")
    print(f"  {'-'*len(header)}")

    for r in results:
        flag = " *" if r["return_on_premium"] < -0.5 else ""
        if has_legs:
            print(f"  " + col.format(
                r["entry_date"], r["exit_date"], r["days_held"],
                f"{r['qqq_return']:+.1%}",
                f"x{r.get('n_legs', 1)}",
                f"${r['premium_paid']:,.0f}",
                f"${r['pnl']:+,.0f}",
                f"{r['return_on_premium']:+.0%}",
            ) + flag)
        else:
            print(f"  " + col.format(
                r["entry_date"], r["exit_date"], r["days_held"],
                f"{r['qqq_return']:+.1%}",
                f"{r['vix_at_entry']:.0f}",
                f"${r['strike_K']:.0f}",
                f"${r['premium_paid']:,.0f}",
                f"${r['pnl']:+,.0f}",
                f"{r['return_on_premium']:+.0%}",
            ) + flag)

    if not results:
        print("  No regimes found.")
        return

    df = pd.DataFrame(results)
    wins      = (df["pnl"] > 0).sum()
    n         = len(df)
    total_pnl = df["pnl"].sum()
    median_rop = df["return_on_premium"].median()
    mean_rop   = df["return_on_premium"].mean()
    total_prem = df["premium_paid"].sum()

    print(f"\n  {'─'*60}")
    print(f"  Regimes:          {n}")
    print(f"  Win rate:         {wins}/{n} = {wins/n:.0%}")
    print(f"  Total premium:    ${total_prem:,.0f}")
    print(f"  Total P&L:        ${total_pnl:+,.0f}  ({total_pnl/total_prem:+.0%} on premium)")
    print(f"  Median RoP:       {median_rop:+.0%}")
    print(f"  Mean RoP:         {mean_rop:+.0%}")
    print(f"  Best regime:      {df['return_on_premium'].max():+.0%}")
    print(f"  Worst regime:     {df['return_on_premium'].min():+.0%}")
    print(f"  * = lost >50% of premium")


def _plot(results_by_delta, budget_frac, iv_shock):
    if not results_by_delta:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: P&L per regime per delta
    ax = axes[0]
    width = 0.25
    deltas = list(results_by_delta.keys())
    all_entries = sorted({r["entry_date"] for rows in results_by_delta.values() for r in rows})
    x = np.arange(len(all_entries))
    colors = ["#2196F3", "#FF9800", "#4CAF50"]

    for i, (delta, rows) in enumerate(results_by_delta.items()):
        by_entry = {r["entry_date"]: r["return_on_premium"] for r in rows}
        vals = [by_entry.get(e, 0) for e in all_entries]
        ax.bar(x + i * width, [v * 100 for v in vals], width,
               label=f"Δ{delta:.2f}", color=colors[i % len(colors)], alpha=0.85)

    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x + width)
    ax.set_xticklabels([e[:7] for e in all_entries], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Return on premium (%)")
    ax.set_title(f"RoP per regime by delta  [{budget_frac:.0%} budget/regime"
                 + (f", IV{iv_shock:+.0%}" if iv_shock else "") + "]")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # Right: cumulative P&L
    ax2 = axes[1]
    for i, (delta, rows) in enumerate(results_by_delta.items()):
        df = pd.DataFrame(rows).sort_values("entry_date")
        cumulative = df["pnl"].cumsum()
        ax2.plot(range(len(cumulative)), cumulative.values,
                 marker="o", ms=4, label=f"Δ{delta:.2f}", color=colors[i % len(colors)])

    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xlabel("Regime #")
    ax2.set_ylabel("Cumulative P&L ($)")
    ax2.set_title("Cumulative option P&L across regimes")
    ax2.legend()
    ax2.grid(alpha=0.3)

    fig.suptitle(f"QQQ Call Overlay — SPMO Signal, {budget_frac:.0%} budget/regime",
                 fontsize=11)
    plt.tight_layout()
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_backtest_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}")


# ---------------------------------------------------------------------------
# Budget sweep
# ---------------------------------------------------------------------------

SWEEP_BUDGETS = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]


def budget_sweep(target_delta=0.50, capital=100_000, iv_shock=0.0, roll_dte=ROLL_DTE):
    """
    Run combined_analysis across SWEEP_BUDGETS for a fixed delta.
    Returns list of metric dicts, one per budget fraction.
    """
    from core.metrics import calc

    rows = []
    margin_eq = None   # same for all budgets — compute once

    for bf in SWEEP_BUDGETS:
        m_eq, o_eq, events = combined_analysis(
            target_delta=target_delta, budget_frac=bf,
            capital=capital, iv_shock=iv_shock, roll_dte=roll_dte,
        )
        if margin_eq is None:
            margin_eq = m_eq

        m = calc(m_eq)
        o = calc(o_eq)
        total_pnl  = sum(e["pnl"]  for e in events)
        total_prem = sum(e["prem"] for e in events)
        wins = sum(1 for e in events if e["pnl"] > 0)
        n    = len(events)

        rows.append({
            "budget_frac":    bf,
            "total_return":   o_eq.iloc[-1] / capital - 1,
            "cagr":           o["cagr"],
            "sharpe":         o["sharpe"],
            "max_dd":         o["max_dd"],
            "cagr_lift":      o["cagr"] - m["cagr"],
            "dd_change":      o["max_dd"] - m["max_dd"],
            "total_prem":     total_prem,
            "option_pnl":     total_pnl,
            "rop":            total_pnl / total_prem if total_prem else 0,
            "win_rate":       wins / n if n else 0,
            "equity":         o_eq,
        })

    return margin_eq, rows


def _print_sweep(margin_eq, sweep_rows, target_delta, capital, iv_shock):
    from core.metrics import calc
    m = calc(margin_eq)
    shock_str = f"  [IV shock: {iv_shock:+.0%}]" if iv_shock else ""

    print(f"\n{'='*90}")
    print(f"  Budget sweep — QQQ Δ{target_delta:.2f} calls over SPMO bull regimes{shock_str}")
    print(f"  Margin-only baseline: CAGR {m['cagr']:.1%}, Sharpe {m['sharpe']:.2f}, "
          f"MaxDD {m['max_dd']:.1%}")
    print(f"{'='*90}")

    hdr = ("{:<8} {:>10} {:>7} {:>8} {:>9} {:>9} {:>9} {:>10} {:>8} {:>8}")
    print("\n  " + hdr.format(
        "Budget", "Tot return", "CAGR", "Sharpe", "MaxDD",
        "CAGR lift", "DD chg", "Opt P&L $", "RoP", "Win%"))
    print("  " + "─" * 88)

    for r in sweep_rows:
        lift_flag = "  ▲" if r["cagr_lift"] > 0 else "   "
        dd_flag   = "  ▼" if r["dd_change"] < 0 else "   "   # ▼ = drawdown improved
        print("  " + hdr.format(
            f"{r['budget_frac']:.0%}",
            f"{r['total_return']:.1%}",
            f"{r['cagr']:.1%}",
            f"{r['sharpe']:.2f}",
            f"{r['max_dd']:.1%}",
            f"{r['cagr_lift']:+.1%}" + lift_flag,
            f"{r['dd_change']:+.1%}" + dd_flag,
            f"${r['option_pnl']:+,.0f}",
            f"{r['rop']:+.0%}",
            f"{r['win_rate']:.0%}",
        ))


def _plot_sweep(margin_eq, sweep_rows, target_delta, capital):
    budgets = [r["budget_frac"] for r in sweep_rows]
    cagrs   = [r["cagr"] * 100 for r in sweep_rows]
    sharpes = [r["sharpe"] for r in sweep_rows]
    dds     = [r["max_dd"] * 100 for r in sweep_rows]
    lifts   = [r["cagr_lift"] * 100 for r in sweep_rows]
    labels  = [f"{b:.0%}" for b in budgets]

    fig = plt.figure(figsize=(16, 10))
    gs  = fig.add_gridspec(2, 3, hspace=0.4, wspace=0.35)

    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(sweep_rows)))

    # top-left: equity curves
    ax_eq = fig.add_subplot(gs[0, :2])
    from core.metrics import calc
    m = calc(margin_eq)
    ax_eq.plot(margin_eq.index, margin_eq.values,
               color="steelblue", lw=2, label=f"Margin only  CAGR {m['cagr']:.1%}")
    for i, r in enumerate(sweep_rows):
        eq = r["equity"]
        ax_eq.plot(eq.index, eq.values, color=colors[i], lw=1.2, alpha=0.85,
                   label=f"{r['budget_frac']:.0%}  CAGR {r['cagr']:.1%}")
    ax_eq.set_title(f"Equity curves — margin + QQQ Δ{target_delta:.2f} calls by budget")
    ax_eq.set_ylabel("Portfolio value ($)")
    ax_eq.legend(fontsize=7, ncol=2)
    ax_eq.grid(alpha=0.3)
    ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # top-right: CAGR lift bar
    ax_lift = fig.add_subplot(gs[0, 2])
    bar_colors = ["green" if v >= 0 else "red" for v in lifts]
    ax_lift.bar(labels, lifts, color=bar_colors, alpha=0.8)
    ax_lift.axhline(0, color="black", lw=0.8)
    ax_lift.set_title("CAGR lift vs margin only")
    ax_lift.set_ylabel("CAGR lift (pp)")
    ax_lift.tick_params(axis="x", rotation=45)
    ax_lift.grid(axis="y", alpha=0.3)

    # bottom-left: CAGR
    ax_cagr = fig.add_subplot(gs[1, 0])
    ax_cagr.plot(labels, cagrs, marker="o", color="darkorange")
    ax_cagr.axhline(m["cagr"] * 100, color="steelblue", lw=1, linestyle="--",
                    label="margin only")
    ax_cagr.set_title("CAGR vs budget")
    ax_cagr.set_ylabel("CAGR (%)")
    ax_cagr.tick_params(axis="x", rotation=45)
    ax_cagr.legend(fontsize=8)
    ax_cagr.grid(alpha=0.3)

    # bottom-mid: Sharpe
    ax_sh = fig.add_subplot(gs[1, 1])
    ax_sh.plot(labels, sharpes, marker="o", color="green")
    from core.metrics import calc as _calc
    ax_sh.axhline(m["sharpe"], color="steelblue", lw=1, linestyle="--",
                  label="margin only")
    ax_sh.set_title("Sharpe vs budget")
    ax_sh.set_ylabel("Sharpe ratio")
    ax_sh.tick_params(axis="x", rotation=45)
    ax_sh.legend(fontsize=8)
    ax_sh.grid(alpha=0.3)

    # bottom-right: MaxDD
    ax_dd = fig.add_subplot(gs[1, 2])
    ax_dd.plot(labels, dds, marker="o", color="crimson")
    ax_dd.axhline(m["max_dd"] * 100, color="steelblue", lw=1, linestyle="--",
                  label="margin only")
    ax_dd.set_title("Max drawdown vs budget")
    ax_dd.set_ylabel("Max drawdown (%)")
    ax_dd.tick_params(axis="x", rotation=45)
    ax_dd.legend(fontsize=8)
    ax_dd.grid(alpha=0.3)

    fig.suptitle(f"Budget sweep — QQQ Δ{target_delta:.2f} calls on $100K portfolio",
                 fontsize=12)
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_sweep_{date.today()}.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Chart saved to {out}")


# ---------------------------------------------------------------------------
# Options-only backtest (no margin leg)
# ---------------------------------------------------------------------------

def options_only_backtest(target_delta=0.50, budget_frac=0.10, capital=100_000,
                          iv_shock=0.0, roll_dte=ROLL_DTE):
    """
    Pure options strategy: capital sits in cash (earning T-bill rate) between
    regimes and between rolls. On each SPMO bull flip, spend budget_frac of
    current cash on QQQ calls. Roll at roll_dte DTE. No margin leg at all.
    """
    spmo, qqq, vix, signal = _fetch_all()
    regimes = _get_regimes(signal)
    all_dates = qqq.index
    daily_cash_rate = RISK_FREE_RATE / 252

    # collect all leg-level cash flow events keyed by date
    # format: {date: [(+/- amount, label), ...]}
    cash_flows = {}
    regime_events = []

    cash = float(capital)
    for start, end in regimes:
        sub_trades, agg = simulate_regime_with_rolls(
            start, end, qqq, vix, target_delta, budget_frac,
            cash, iv_shock, roll_dte)
        if not sub_trades:
            continue

        for leg in sub_trades:
            ed = pd.Timestamp(leg["entry_date"])
            xd = pd.Timestamp(leg["exit_date"])
            cash_flows.setdefault(ed, []).append(-leg["premium_paid"])
            cash_flows.setdefault(xd, []).append(+leg["proceeds"])

        # update cash with net regime outcome
        cash += agg["total_pnl"]

        regime_events.append({
            "entry":             agg["entry_date"],
            "exit":              agg["exit_date"],
            "n_legs":            agg["n_legs"],
            "qqq_return":        agg["regime_qqq_return"],
            "premium_paid":      agg["total_premium"],
            "proceeds":          agg["total_proceeds"],
            "pnl":               agg["total_pnl"],
            "return_on_premium": agg["return_on_premium"],
            "cash_after":        round(cash, 2),
        })

    # build daily equity curve
    cash = float(capital)
    active_premium = 0.0   # track premium currently deployed (mark-at-cost)
    active_legs = {}       # leg entry_date -> premium (for tracking active exposure)

    eq_vals = []
    for dt in all_dates:
        flows = cash_flows.get(dt, [])
        for amt in flows:
            if amt < 0:
                # premium out — option bought
                active_premium += abs(amt)
                cash += amt
            else:
                # proceeds in — option closed/expired
                # reduce active premium by the original cost of the leg that just closed
                # (approximate: reduce proportionally)
                active_premium = max(0.0, active_premium - abs(amt) * 0.5)
                cash += amt

        cash *= (1 + daily_cash_rate)
        eq_vals.append(cash + active_premium)

    equity = pd.Series(eq_vals, index=all_dates)
    return equity, regime_events


def _print_yearly(equity, benchmark_dict: dict, label: str = "Strategy"):
    """
    Print a year-by-year return table.
    benchmark_dict: {name: equity_series} — printed alongside strategy.
    """
    years = sorted(set(equity.index.year))
    bench_names = list(benchmark_dict.keys())

    hdr = f"  {'Year':<6} {label:>12}"
    for b in bench_names:
        hdr += f"  {b:>12}"
    hdr += f"  {'vs ' + bench_names[0]:>10}" if bench_names else ""
    print(f"\n{hdr}")
    print(f"  {'─' * (len(hdr) - 2)}")

    for yr in years:
        s = equity[equity.index.year == yr]
        if len(s) < 2:
            continue
        ret = s.iloc[-1] / s.iloc[0] - 1
        row = f"  {yr:<6} {ret:>12.1%}"
        first_bench_ret = None
        for i, (name, beq) in enumerate(benchmark_dict.items()):
            b = beq[beq.index.year == yr]
            if len(b) < 2:
                row += f"  {'—':>12}"
                continue
            bret = b.iloc[-1] / b.iloc[0] - 1
            row += f"  {bret:>12.1%}"
            if i == 0:
                first_bench_ret = bret
        if first_bench_ret is not None:
            row += f"  {ret - first_bench_ret:>+10.1%}"
        print(row)


def _print_options_only(equity, events, capital, target_delta, budget_frac, iv_shock):
    from core.metrics import calc

    m = calc(equity)
    total_return = equity.iloc[-1] / capital - 1
    total_pnl  = sum(e["pnl"]  for e in events)
    total_prem = sum(e["premium_paid"] for e in events)
    wins = sum(1 for e in events if e["pnl"] > 0)
    n    = len(events)

    shock_str = f"  [IV shock: {iv_shock:+.0%}]" if iv_shock else ""
    print(f"\n{'='*80}")
    print(f"  Options-only backtest — QQQ Δ{target_delta:.2f}, {budget_frac:.0%}/regime{shock_str}")
    print(f"  Signal: SPMO MA{PORTFOLIO[SIGNAL_TICKER]['ma_fast']}/"
          f"{PORTFOLIO[SIGNAL_TICKER]['ma_slow']}  |  "
          f"Cash earns T-bill rate ({RISK_FREE_RATE:.1%}/yr) between regimes")
    print(f"{'='*80}")

    col = "{:<12} {:<12} {:>5} {:>8} {:>6} {:>10} {:>9} {:>9} {:>10}"
    header = col.format("Entry", "Exit", "Days", "QQQ ret", "Legs",
                        "Prem $", "P&L $", "RoP", "Cash after")
    print(f"\n  {header}")
    print(f"  {'-'*len(header)}")
    for e in events:
        print("  " + col.format(
            e["entry"], e["exit"],
            (pd.Timestamp(e["exit"]) - pd.Timestamp(e["entry"])).days,
            f"{e['qqq_return']:+.1%}",
            f"x{e.get('n_legs', 1)}",
            f"${e['premium_paid']:,.0f}",
            f"${e['pnl']:+,.0f}",
            f"{e['return_on_premium']:+.0%}",
            f"${e['cash_after']:,.0f}",
        ))

    print(f"\n  {'─'*60}")
    print(f"  Starting capital:   ${capital:,.0f}")
    print(f"  Final equity:       ${equity.iloc[-1]:,.0f}")
    print(f"  Total return:       {total_return:.1%}")
    print(f"  CAGR:               {m['cagr']:.1%}")
    print(f"  Sharpe:             {m['sharpe']:.2f}")
    print(f"  Max drawdown:       {m['max_dd']:.1%}")
    print(f"  Regimes traded:     {n}")
    print(f"  Win rate:           {wins}/{n} = {wins/n:.0%}")
    print(f"  Total premium:      ${total_prem:,.0f}")
    print(f"  Net option P&L:     ${total_pnl:+,.0f}  ({total_pnl/total_prem:+.0%} on premium)")

    # year-by-year vs QQQ B&H
    qqq = fetch(CALL_TICKER)
    bah = capital * qqq / qqq.iloc[0]
    bah = bah.reindex(equity.index).ffill()
    _print_yearly(equity, {"QQQ B&H": bah}, label="Options-only")


def _plot_options_only(equity, capital, target_delta, budget_frac):
    from core.metrics import calc

    # QQQ buy-and-hold benchmark over same period
    qqq = fetch(CALL_TICKER)
    qqq = qqq.reindex(equity.index).dropna()
    bah = capital * qqq / qqq.iloc[0]
    bah = bah.reindex(equity.index).ffill()

    # T-bill only (pure cash, no options) — shows option contribution vs doing nothing
    daily_rate = RISK_FREE_RATE / 252
    cash_only  = pd.Series(
        [capital * (1 + daily_rate) ** i for i in range(len(equity))],
        index=equity.index,
    )

    m_opt = calc(equity)
    m_bah = calc(bah.reindex(equity.index).dropna())

    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                             gridspec_kw={"height_ratios": [3, 1]})

    ax = axes[0]
    ax.plot(equity.index, equity.values, color="darkorange", lw=1.8,
            label=f"Options only  CAGR {m_opt['cagr']:.1%}, Sharpe {m_opt['sharpe']:.2f}")
    ax.plot(bah.index, bah.values, color="steelblue", lw=1.5, alpha=0.8,
            label=f"QQQ B&H  CAGR {m_bah['cagr']:.1%}")
    ax.plot(cash_only.index, cash_only.values, color="gray", lw=1, linestyle="--",
            label=f"T-bill cash  ({RISK_FREE_RATE:.1%}/yr)")
    ax.set_title(f"Options-only strategy — QQQ Δ{target_delta:.2f} calls, "
                 f"{budget_frac:.0%} budget per SPMO bull regime")
    ax.set_ylabel("Portfolio value ($)")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # bottom: drawdown
    ax2 = axes[1]
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max * 100
    ax2.fill_between(dd.index, dd.values, 0, color="crimson", alpha=0.4)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_title("Options-only drawdown")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_only_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}")


def options_only_sweep(target_delta=0.50, capital=100_000, iv_shock=0.0, roll_dte=ROLL_DTE):
    """Sweep budget fractions for the options-only strategy."""
    from core.metrics import calc

    qqq = fetch(CALL_TICKER)
    rows = []
    for bf in SWEEP_BUDGETS:
        eq, events = options_only_backtest(target_delta, bf, capital, iv_shock, roll_dte)
        m = calc(eq)
        total_pnl  = sum(e["pnl"] for e in events)
        total_prem = sum(e["premium_paid"] for e in events)
        wins = sum(1 for e in events if e["pnl"] > 0)
        rows.append({
            "budget_frac":  bf,
            "total_return": eq.iloc[-1] / capital - 1,
            "cagr":         m["cagr"],
            "sharpe":       m["sharpe"],
            "max_dd":       m["max_dd"],
            "option_pnl":   total_pnl,
            "rop":          total_pnl / total_prem if total_prem else 0,
            "win_rate":     sum(1 for e in events if e["pnl"] > 0) / len(events),
            "equity":       eq,
        })

    # QQQ B&H benchmark
    eq0 = rows[0]["equity"]
    qqq_a = qqq.reindex(eq0.index).dropna()
    bah = capital * qqq_a / qqq_a.iloc[0]
    bah_m = calc(bah)

    shock_str = f"  [IV shock: {iv_shock:+.0%}]" if iv_shock else ""
    print(f"\n{'='*85}")
    print(f"  Options-only budget sweep — QQQ Δ{target_delta:.2f} calls{shock_str}")
    print(f"  QQQ B&H benchmark: CAGR {bah_m['cagr']:.1%}, "
          f"Sharpe {bah_m['sharpe']:.2f}, MaxDD {bah_m['max_dd']:.1%}")
    print(f"{'='*85}")

    hdr = "{:<8} {:>10} {:>7} {:>8} {:>9} {:>10} {:>8} {:>8}"
    print("\n  " + hdr.format("Budget", "Tot return", "CAGR", "Sharpe",
                               "MaxDD", "Opt P&L $", "RoP", "Win%"))
    print("  " + "─" * 72)
    for r in rows:
        beat = "  ✓" if r["cagr"] > bah_m["cagr"] else "   "
        print("  " + hdr.format(
            f"{r['budget_frac']:.0%}",
            f"{r['total_return']:.1%}",
            f"{r['cagr']:.1%}" + beat,
            f"{r['sharpe']:.2f}",
            f"{r['max_dd']:.1%}",
            f"${r['option_pnl']:+,.0f}",
            f"{r['rop']:+.0%}",
            f"{r['win_rate']:.0%}",
        ))

    # fetch SPMO for signal panel
    from signals import ma as sig_ma
    spmo = fetch(SIGNAL_TICKER)
    cfg  = PORTFOLIO[SIGNAL_TICKER]
    spmo_signal = sig_ma.signal(spmo, cfg["ma_fast"], cfg["ma_slow"])
    ma_fast_s = spmo.rolling(cfg["ma_fast"]).mean()
    ma_slow_s = spmo.rolling(cfg["ma_slow"]).mean()
    regimes   = _get_regimes(spmo_signal)

    # two-panel layout: equity curves (top) + SPMO signal (bottom)
    fig, axes = plt.subplots(2, 1, figsize=(14, 9),
                             gridspec_kw={"height_ratios": [3, 1.2]},
                             sharex=True)

    # --- top: equity curves ---
    ax = axes[0]
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(rows)))
    ax.plot(bah.index, bah.values, color="steelblue", lw=2,
            label=f"QQQ B&H  CAGR {bah_m['cagr']:.1%}")
    for i, r in enumerate(rows):
        ax.plot(r["equity"].index, r["equity"].values, color=colors[i], lw=1.2,
                label=f"{r['budget_frac']:.0%}  CAGR {r['cagr']:.1%}")

    # shade bull regimes on equity panel too
    for start, end in regimes:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end),
                   alpha=0.07, color="green", linewidth=0)

    ax.set_title(f"Options-only — QQQ Δ{target_delta:.2f}, budget sweep vs QQQ B&H\n"
                 f"(green shading = SPMO bull regime, calls active)")
    ax.set_ylabel("Portfolio value ($)")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # --- bottom: SPMO price + MAs + regime shading ---
    ax2 = axes[1]
    common = spmo.index.intersection(eq0.index)
    ax2.plot(common, spmo.reindex(common).values,
             color="black", lw=1.2, label="SPMO price")
    ax2.plot(common, ma_fast_s.reindex(common).values,
             color="darkorange", lw=1, linestyle="--",
             label=f"MA{cfg['ma_fast']}")
    ax2.plot(common, ma_slow_s.reindex(common).values,
             color="crimson", lw=1, linestyle="--",
             label=f"MA{cfg['ma_slow']}")

    for start, end in regimes:
        ax2.axvspan(pd.Timestamp(start), pd.Timestamp(end),
                    alpha=0.15, color="green", linewidth=0)

    ax2.set_ylabel("SPMO price ($)")
    ax2.set_title(f"SPMO signal (MA{cfg['ma_fast']}/{cfg['ma_slow']}) — "
                  f"green = bull regime (calls active)")
    ax2.legend(fontsize=8, loc="upper left")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_only_sweep_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def strategy_compare(target_delta=0.50, budget_frac=0.03, capital=100_000,
                     iv_shock=0.0, roll_dte=ROLL_DTE):
    """
    Print a side-by-side comparison of all three strategy variants:
      1. Margin-only (SPMO 80% + GLD 20%, 2x leverage)
      2. Options-only (QQQ calls + T-bill cash)
      3. Combined (margin + call overlay)

    Also prints a unified year-by-year table.
    """
    from core.metrics import calc

    print(f"\n{'='*72}")
    print(f"  Strategy comparison  —  Δ{target_delta:.2f} calls, {budget_frac:.0%}/regime budget")
    print(f"  Signal: SPMO MA{PORTFOLIO[SIGNAL_TICKER]['ma_fast']}/"
          f"{PORTFOLIO[SIGNAL_TICKER]['ma_slow']}  |  capital: ${capital:,.0f}")
    print(f"{'='*72}")

    # 1. margin only
    margin_eq, overlay_eq, _ = combined_analysis(
        target_delta=target_delta, budget_frac=budget_frac,
        capital=capital, iv_shock=iv_shock, roll_dte=roll_dte,
    )
    m_margin = calc(margin_eq)

    # 2. options only
    opt_eq, _ = options_only_backtest(
        target_delta=target_delta, budget_frac=0.10,
        capital=capital, iv_shock=iv_shock, roll_dte=roll_dte,
    )
    m_opt = calc(opt_eq)

    # 3. combined
    m_comb = calc(overlay_eq)

    # QQQ B&H as external baseline
    qqq = fetch(CALL_TICKER)
    bah = capital * qqq / qqq.iloc[0]
    bah = bah.reindex(margin_eq.index).ffill()
    m_bah = calc(bah.dropna())

    cols = ["Margin only", "Options-only\n(10%/regime)", "Combined\n(margin+3%)", "QQQ B&H"]
    metrics_list = [m_margin, m_opt, m_comb, m_bah]
    label_col = 22

    def row(name, vals):
        return f"  {name:<{label_col}}" + "".join(f"{v:>16}" for v in vals)

    print(f"\n  {'':22}" + "".join(f"{'Margin only':>16}") +
          f"{'Opt-only 10%':>16}{'Combined 3%':>16}{'QQQ B&H':>16}")
    print(f"  {'─' * 86}")
    print(row("CAGR", [f"{m['cagr']:.1%}" for m in metrics_list]))
    print(row("Sharpe", [f"{m['sharpe']:.2f}" for m in metrics_list]))
    print(row("Max drawdown", [f"{m['max_dd']:.1%}" for m in metrics_list]))
    print(row("Total return", [f"{m['total']:.1%}" for m in metrics_list]))
    print(row("Final equity", [f"${capital * (1 + m['total']):,.0f}" for m in metrics_list]))

    # year-by-year
    print(f"\n  {'Year':<6} {'Margin':>10} {'Opt-only':>10} {'Combined':>10} {'QQQ B&H':>10}")
    print(f"  {'─' * 50}")
    for yr in sorted(set(margin_eq.index.year)):
        def yr_ret(eq):
            s = eq[eq.index.year == yr]
            return f"{s.iloc[-1]/s.iloc[0]-1:+.1%}" if len(s) >= 2 else "—"
        print(f"  {yr:<6} {yr_ret(margin_eq):>10} {yr_ret(opt_eq):>10} "
              f"{yr_ret(overlay_eq):>10} {yr_ret(bah):>10}")

    # chart: three equity curves
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(margin_eq.index, margin_eq.values, color="steelblue",  lw=1.5,
            label=f"Margin only  CAGR {m_margin['cagr']:.1%}")
    ax.plot(opt_eq.index,    opt_eq.values,    color="darkorange", lw=1.5,
            label=f"Options-only (10%)  CAGR {m_opt['cagr']:.1%}")
    ax.plot(overlay_eq.index, overlay_eq.values, color="green",   lw=1.5,
            label=f"Combined (3%)  CAGR {m_comb['cagr']:.1%}")
    ax.plot(bah.index, bah.values, color="gray", lw=1.0, linestyle="--",
            label=f"QQQ B&H  CAGR {m_bah['cagr']:.1%}")
    ax.set_ylabel("Portfolio value ($)")
    ax.set_title(f"Strategy comparison  —  QQQ Δ{target_delta:.2f}, {budget_frac:.0%} budget\n"
                 f"Margin-only vs Options-only vs Combined vs QQQ B&H")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    plt.tight_layout()
    CHART_DIR.mkdir(exist_ok=True)
    out = CHART_DIR / f"options_compare_{date.today()}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print(f"\n  Chart saved to {out}\n")


def _parse_args():
    args = sys.argv[1:]
    delta        = 0.50
    budget       = 0.10
    shock        = 0.0
    roll         = ROLL_DTE
    combined     = False
    sweep        = False
    options_only = False
    compare      = False
    i = 0
    while i < len(args):
        if args[i] == "--delta" and i + 1 < len(args):
            delta = float(args[i + 1]); i += 2
        elif args[i] == "--budget" and i + 1 < len(args):
            budget = float(args[i + 1]); i += 2
        elif args[i] == "--iv-shock" and i + 1 < len(args):
            shock = float(args[i + 1]); i += 2
        elif args[i] == "--roll-dte" and i + 1 < len(args):
            roll = int(args[i + 1]); i += 2
        elif args[i] == "--combined":
            combined = True; i += 1
        elif args[i] == "--sweep":
            sweep = True; i += 1
        elif args[i] == "--options-only":
            options_only = True; i += 1
        elif args[i] == "--compare":
            compare = True; i += 1
        else:
            i += 1
    return delta, budget, shock, roll, combined, sweep, options_only, compare


if __name__ == "__main__":
    target_delta, budget_frac, iv_shock, roll_dte, show_combined, show_sweep, show_options_only, show_compare = _parse_args()
    capital = 100_000

    if show_compare:
        strategy_compare(target_delta=target_delta, budget_frac=budget_frac,
                         capital=capital, iv_shock=iv_shock, roll_dte=roll_dte)

    elif show_options_only:
        if show_sweep:
            options_only_sweep(target_delta=target_delta, capital=capital,
                               iv_shock=iv_shock, roll_dte=roll_dte)
        else:
            equity, events = options_only_backtest(
                target_delta=target_delta, budget_frac=budget_frac,
                capital=capital, iv_shock=iv_shock, roll_dte=roll_dte,
            )
            _print_options_only(equity, events, capital, target_delta, budget_frac, iv_shock)
            _plot_options_only(equity, capital, target_delta, budget_frac)

    elif show_sweep:
        print(f"  Sweeping budget fractions for QQQ Δ{target_delta:.2f} calls "
              f"(roll at {roll_dte} DTE)...")
        margin_eq, sweep_rows = budget_sweep(
            target_delta=target_delta, capital=capital, iv_shock=iv_shock,
            roll_dte=roll_dte)
        _print_sweep(margin_eq, sweep_rows, target_delta, capital, iv_shock)
        _plot_sweep(margin_eq, sweep_rows, target_delta, capital)

    elif show_combined:
        margin_eq, overlay_eq, events = combined_analysis(
            target_delta=target_delta, budget_frac=budget_frac,
            capital=capital, iv_shock=iv_shock, roll_dte=roll_dte,
        )
        _print_combined(margin_eq, overlay_eq, events,
                        target_delta, budget_frac, capital)
        _plot_combined(margin_eq, overlay_eq, target_delta, budget_frac)

    else:
        all_deltas = [0.85, 0.50, 0.30]
        results_by_delta = {}
        for d in all_deltas:
            rows = run(target_delta=d, budget_frac=budget_frac,
                       capital=capital, iv_shock=iv_shock, roll_dte=roll_dte)
            results_by_delta[d] = rows

        for d in all_deltas:
            _print_results(results_by_delta[d], d, budget_frac, iv_shock)

        _plot(results_by_delta, budget_frac, iv_shock)

        if iv_shock == 0.0:
            print(f"\n{'─'*60}")
            print("  IV sensitivity: rerunning with +20% IV shock at entry")
            print(f"{'─'*60}")
            for d in all_deltas:
                rows_shocked = run(target_delta=d, budget_frac=budget_frac,
                                   capital=capital, iv_shock=0.20, roll_dte=roll_dte)
                _print_results(rows_shocked, d, budget_frac, iv_shock=0.20)
