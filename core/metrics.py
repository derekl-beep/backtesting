import pandas as pd


def calc(equity: pd.Series) -> dict:
    """Compute performance metrics from an equity curve."""
    ret = equity.pct_change().dropna()
    n_years = len(ret) / 252
    total = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    sharpe = ret.mean() / ret.std() * (252 ** 0.5) if ret.std() > 0 else 0.0
    max_dd = (equity / equity.cummax() - 1).min()
    return {"total": total, "cagr": cagr, "sharpe": sharpe, "max_dd": max_dd}


def print_comparison(ticker: str, bah: dict, strat: dict, margin_calls: int, total_fees: float):
    print(f"\n{'='*40}")
    print(f" {ticker}")
    print(f"{'='*40}")
    print(f"  {'':30s} {'Buy&Hold':>10} {'Strategy':>10}")
    print(f"  {'Total return':30s} {bah['total']:>10.1%} {strat['total']:>10.1%}")
    print(f"  {'CAGR':30s} {bah['cagr']:>10.1%} {strat['cagr']:>10.1%}")
    print(f"  {'Sharpe ratio':30s} {bah['sharpe']:>10.2f} {strat['sharpe']:>10.2f}")
    print(f"  {'Max drawdown':30s} {bah['max_dd']:>10.1%} {strat['max_dd']:>10.1%}")
    print(f"  {'Margin calls':30s} {'':>10} {margin_calls:>10}")
    print(f"  {'Total fees':30s} {'':>10} ${total_fees:>9,.2f}")
