# SPMO+GLD Backtester — Workflow & Findings

I dogfooded the whole ETF tool suite end-to-end (seeded a synthetic price cache since live Yahoo Finance access is blocked by this sandbox's egress policy — see caveat at the bottom). Every command below actually ran; output is real, just built on fake prices.

## 1. Setting up a new strategy (research phase)

```
python -m tools.screen <CANDIDATE> SPMO GLD      # correlation + baseline alpha (MA50/100)
python -m tools.optimize <CANDIDATE>              # walk-forward MA search, 2018-2025 OOS folds
python -m tools.optimize --signals ma,rsi <CANDIDATE>   # try richer signals if MA alone is weak
```

`screen` answers "is this worth pursuing at all" (low correlation to existing legs + positive alpha).
`optimize` answers "what params" — pick the row with the highest fold count, tie-break on avg vs B&H.
In my run, `tools.optimize SPMO` recommended MA50/100 (8/8 folds) even though the live config uses MA10/200 (5/8) — expected, since my synthetic series doesn't reproduce the real regime structure the current params were tuned on.

## 2. Adding it to the portfolio

1. Edit `PORTFOLIO` in `core/portfolio_config.py` — weights must sum to 1.0.
2. `python -m tools.portfolio` to confirm the combined curve still looks sane (Sharpe, MaxDD, margin days).
3. `python -m tools.tune` (no `--apply`) to sanity-check the newly added ticker doesn't change the joint-optimal params for the tickers already in the book. Only re-run with `--apply` if the Sharpe verdict says IMPROVED — it gates the config rewrite for you.

## 3. Verifying before trusting a config

```
pytest                                   # pins signal flips, simulator/fee math, golden backtest
python -m tools.sensitivity <TICKER>     # is the param a plateau or an isolated peak?
python -m tools.compare <TICKER>         # does MA-only beat RSI/MACD add-ons after fees?
```

`sensitivity` was the most useful "am I curve-fitting" check — it outlines the current MA cell on a heatmap of neighbors and gives a plain verdict (PLATEAU vs isolated peak), plus a rolling-Sharpe-vs-B&H decay chart. Run this quarterly per the CLAUDE.md guidance, and always before accepting a `tune --apply`.

## 4. Daily operation

```
python -m tools.signal SPMO GLD --alert --threshold 3
```

This is the one command for daily use. It prints per-leg MA/RSI/MACD state, days in regime, distance to flip, position sizing at your capital, and a PORTFOLIO SUMMARY (ALL ON / ALL OFF / MIXED). The `--alert` flag appends a dedup-friendly JSON block (`flipped_today`, `entered_band_today`) — built for wiring into a cron job / notification, not for manual reading.

When margin is on and you want the options overlay too:
```
python -m tools.options_signal --capital <YOUR_CAPITAL>
```
gives the exact contract to buy, sizing at 3/5/10% budget, and unrealized P&L on the current leg.

## 5. Periodic maintenance

- **Quarterly:** `tools.sensitivity` on all portfolio tickers — catches param decay before it costs money.
- **Annually (once — it burns holdout data):** `tools.optimize --final <TICKER>`.
- **Ad hoc, whenever a new candidate ETF comes up:** the "Adding it to the portfolio" flow above.

## Bugs / gaps found while actually running these

| Severity | Where | Issue |
|---|---|---|
| Real bug | `tools/compare.py:47` | If the hardcoded hedge ticker (`SH`) fails to download, `compare.py` crashes with an unhandled `IndexError: single positional indexer is out-of-bounds` instead of the graceful "not enough data" message `tools/signal.py` gives for the same failure mode. Any tool that fetches a ticker the user didn't type (SH here, `^VIX` in options tools) should guard against an empty/short series the same way the user-facing tools do. |
| Consistency bug | `tools/compare.py:143` | Saves its chart to `compare_<ticker>.png` in the repo root instead of `charts/compare/...` like every other tool (`backtest`, `portfolio`, `screen`, `sensitivity` all use `charts/<tool>/`). It's not gitignored at that path either, so it shows up as an untracked file in `git status` after every run — I had to manually delete a stray `compare_spmo.png` from the repo root during this session. |
| Possible bug (needs real-data confirmation) | `tools/sizing.py` | The Calmar/Sharpe-vs-budget table showed byte-identical CAGR/Sharpe/Calmar/MaxDD for every budget from 1% through 10% (only changed at 15%+). Smells like contract-count rounding collapsing several budget fractions onto the same integer contract count at low capital — worth double-checking with real prices/premiums, since it defeats the point of the sweep at the low end. |

## Feature gaps / suggested improvements

- **No offline/synthetic data mode.** Every tool hard-depends on live Yahoo Finance with no way to point at a local CSV/pickle or a fixture dataset. This blocks CI-less "does the CLI still run" smoke testing (like this session had to do) and blocks anyone behind a restrictive proxy/firewall. A `--data-dir` or `BACKTEST_DATA_SOURCE=local` escape hatch pointing at the existing `data/{ticker}.pkl` cache format would fix both.
- **No single "run everything and tell me if anything looks wrong" command.** The daily workflow is really just `tools.signal --alert`, but the maintenance workflow is five separate manual invocations (`sensitivity`, `compare`, `tune`, `screen`, `optimize --final`) that a user has to remember to run on the right cadence. A `tools.healthcheck` that runs sensitivity + tune (dry-run) + pytest and prints one summary would reduce the chance of param decay going unnoticed between quarters.
- **No data source health check.** When yfinance fails, several tools (`backtest`, `signal` without `--alert`) print noisy tracebacks/warnings but still exit 0 with "not enough data" — silent-ish failure in a script/cron context. A fetch-layer check that exits non-zero (or emits a clear `DATA_FETCH_FAILED` marker) would make the daily alert cron fail loudly instead of quietly reporting stale/no signal.
- **Chart output paths are inconsistent** (see bug table above) — worth a quick audit of every tool's `savefig` call against the documented `charts/<tool>/` convention.

## Caveat on this session's testing

This sandbox's outbound proxy returns HTTP 403 for `fc.yahoo.com` (confirmed via the proxy's own status endpoint — an explicit organization policy denial, not a transient error), so yfinance cannot reach real market data here. To actually exercise the CLI rather than just import-check it, I generated synthetic random-walk price series for every ticker the tools touch (SPMO, GLD, QQQ, SPY, TLT, EEM, IWM, EWJ, NUKZ, VGT, VOO, SH, ^VIX) and wrote them directly into the `data/{ticker}.pkl` cache format `core/data.py` already expects. All numeric output above (CAGRs, Sharpes, recommended params) is **synthetic and not a real trading signal** — only the mechanics (does it run, does the workflow make sense, where does it break) are meaningful findings. I deleted the synthetic cache and generated charts afterward so no fake data or fake charts are left in your working tree.
