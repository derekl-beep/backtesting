# Research Log

Running record of experiments, rejected candidates, and findings.
Use this before re-testing an idea — it may already have been tried.

Previously a single `RESEARCH.md` file; split 2026-07-04 into topic files as the
log passed ~1000 lines. Read **methodology.md first** — it's the single finding
that reframes how to read every other file's "alpha" numbers.

| File | Contents |
|------|----------|
| [methodology.md](methodology.md) | The core finding: reported "alpha" is a leverage-timing effect, not signal quality. Read this first. |
| [etf_candidates.md](etf_candidates.md) | Every ETF screened for the portfolio: accepted, rejected, and why. Includes 2026-07-04's new-ticker research. |
| [portfolio_construction.md](portfolio_construction.md) | Allocation-level experiments (e.g. dynamic GLD weighting). |
| [signal_configs.md](signal_configs.md) | MA window selection, multi-signal combos, sensitivity heatmap baseline. |
| [options_overlay.md](options_overlay.md) | The QQQ/SMH call-options overlay: concept, sizing, rolling model, real-chain validation, bootstrap CIs, parameter sensitivity, multi-overlay aggregation. |
| [quant_toolbox.md](quant_toolbox.md) | Statistical rigor tools: probabilistic (logistic) regime signal, VaR/CVaR, Monte Carlo forward simulation, circular-shift significance testing. |
| [strategy_experiments.md](strategy_experiments.md) | Standalone strategy variants tested against the roadmap: spreads, covered calls, bear-regime puts, sector rotation. |
| [open_questions.md](open_questions.md) | What's still open for the next research session. |

## The one-paragraph summary

Every "alpha" number in this project compares a 2x-leveraged strategy against a
1x buy-and-hold. That's not a stock-picking edge — it's mostly the return from
adding leverage during confirmed uptrends (see methodology.md). Three independent
tests (1x-vs-2x decomposition, circular-shift permutation testing, and a
from-scratch logistic regression signal) all agree: none of this project's
tickers show MA-crossover timing that's statistically distinguishable from
random timing of the same exposure. The portfolio still works — leverage-timing
is a real, structurally low-risk source of return — but it should be described
and sized as that, not as evidence of superior market-timing skill.
