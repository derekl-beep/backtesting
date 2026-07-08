# Harness Diagnosis — 2026-07-07

Written by Claude Fable 5 as the foundation for the agent-system docs in this directory.
Every other file in `docs/agents/` traces back to one of these three weaknesses.
Audience: future Claude sessions on smaller models (Sonnet/Opus/Haiku class).

## Weakness 1 — Token waste: CLAUDE.md was a 575-line monolith loaded every session

**Evidence (measured 2026-07-07):** `CLAUDE.md` was 575 lines / 33,769 bytes (~8,400
tokens), loaded into every session before the first user message. ~450 of those lines were
a per-tool catalog with research findings pasted inline — content that also exists in
`research/*.md`. The most common session type (daily signal check: `tools.signal SPMO GLD`)
needs about 15 of those 575 lines. On top of that, the auto-memory file
`project_spmo_backtest.md` duplicated the architecture tree and command list a third time —
and had already drifted (it described `SIGNAL_CONFIGS` at the top of `tools/signal.py`;
the code moved to `core/portfolio_config.py`).

**Cost:** ~8K tokens of fixed overhead per session, plus re-reading duplicated research
narrative whenever the model greps for context.

**Fix (implemented 2026-07-07):**
- `CLAUDE.md` rewritten as a router: invariants + a "where to look" table (80 lines at
  rewrite; hard ceiling 150 — the single threshold used everywhere).
- Full tool catalog moved to `docs/TOOLS.md` — read on demand, not by default.
- Findings live only in `research/*.md`; `docs/TOOLS.md` links to them instead of restating.
- Memory files trimmed to pointers (memory should record what the repo *can't*: user
  preferences and cross-session context — never architecture or command lists).

**Measurable check:** `wc -l CLAUDE.md` ≤ 150. If it exceeds that, apply the consolidation
protocol in [MAINTENANCE.md](MAINTENANCE.md).

## Weakness 2 — Focus loss: every finding lived in 4–6 places with no designated owner

**Evidence:** the bear-put-overlay result appeared in (1) CLAUDE.md's tool section,
(2) CLAUDE.md's Roadmap, (3) `research/strategy_experiments.md`, (4)
`research/open_questions.md` item #10 — four copies of the same numbers. Drift was already
observable before this rewrite: `README.md`'s roadmap still listed "mean-reversion for
ETFs" as open (answered 2026-07-06), and the project memory file described a pre-refactor
architecture. `docs/WORKFLOW.md` documents three suspected bugs that no other file mentions.

**Cost:** a weaker model updating one copy misses the others; a later session reads the
stale copy and re-tests a rejected idea, cites outdated numbers, or edits the wrong
"source of truth." With real money following these numbers, a stale portfolio-params table
is not cosmetic.

**Fix (implemented 2026-07-07):** a single-source-of-truth ownership table. Every fact type
has exactly one home; everything else may only *point* there.

| Fact type | Only authoritative home |
|---|---|
| Live portfolio weights + signal params | `core/portfolio_config.py` (code, not docs) |
| Broker/fee/leverage constants | `core/config.py` |
| How to run each tool | `docs/TOOLS.md` |
| Research findings, verdicts, rejected ideas | `research/*.md` (index: `research/README.md`) |
| Open/unfinished research questions | `research/open_questions.md` |
| Agent behavior rules (this system) | `docs/agents/*.md` |
| Lessons from mistakes | `docs/agents/LESSONS.md` |
| User preferences | auto-memory `feedback_working_style.md` |

**Measurable check:** before writing a number or finding into any file, ask "is this file
the owner per the table above?" If not, write a link, not a copy. The maintenance audit in
[MAINTENANCE.md](MAINTENANCE.md) greps for drift quarterly.

## Weakness 3 — Mistakes: no mandatory verification gates, and self-validation

**Evidence from this repo's own history (all real, all documented in `research/`):**
- `signals/rsi.py` computed RSI=0 for an uninterrupted uptrend instead of RSI=100 —
  exactly backwards — and shipped that way until 2026-07-06. No test pinned the behavior.
- The first sector-rotation backtest reported CAGR 900–2,300% (monthly data fed into a
  daily-frequency annualizer). Caught only because someone eyeballed the magnitude.
- `tools/optimize.py` silently dropped OOS folds where no combo passed constraints — SMH
  looked "unoptimizable" with no explanation.
- `docs/WORKFLOW.md` documents a crash in `tools/compare.py`, an inconsistent chart path,
  and a suspicious budget-sweep rounding issue — found only when someone finally *ran* the
  tools end-to-end.

The pattern: the failure mode here is almost never "code that errors"; it's **code that runs
and produces a confident wrong number**. Real money follows these numbers. A weaker model is
*more* likely than the model that wrote this to (a) trust a big backtest number without
walk-forward/significance discipline, (b) declare success without executing anything, and
(c) "fix" a failing golden test by updating the pinned value.

**Fix (implemented 2026-07-07):** hard, checkable gates instead of judgment calls:
- After ANY edit under `core/`, `signals/`, `strategies/`, `tools/`, or `tests/`: run
  `.venv/bin/pytest`. A failing golden test means strategy behavior
  changed — stop and report; never update the pinned value to make it pass
  (full rule + exceptions: [JUDGMENT.md](JUDGMENT.md) §5).
- Sanity-range table for backtest output (in [JUDGMENT.md](JUDGMENT.md)): numbers outside
  plausible ranges are treated as bugs until proven otherwise.
- Validation is never self-validation: acceptance checks run in a fresh-context agent per
  [ORCHESTRATION.md](ORCHESTRATION.md) §Validation.
- Deploy/reject decisions on real-money strategy changes always go to Derek — a model
  (any model) does not decide them (see [JUDGMENT.md](JUDGMENT.md) §3).

**Measurable check:** every completed task that touched code must show, in the final
report: the pytest command run and its result, plus at least one actual execution of the
affected tool with output. "Should work" is a failed check.

## Known doc-vs-code discrepancies (fix or refute before trusting)

From `docs/WORKFLOW.md` (found on synthetic data); status updated 2026-07-07 by
source-reading (not execution):

1. `tools/compare.py` — unhandled `IndexError` if the hedge ticker `SH` fails to download.
   *Crash-prone code confirmed present in source; failure behavior not executed.*
2. `tools/compare.py` — **confirmed in source:** saves chart to repo root instead of
   `charts/compare/`, and calls `plt.show()` (violates CLAUDE.md iron rule 5). Fix pending.
3. `tools/sizing.py` — budget fractions 1–10% may collapse to identical results at low
   capital (contract-count rounding), defeating the sweep. *Unverified.*

If a session touches any of these files, verify (and fix or refute) the claim, then update
this list and `docs/WORKFLOW.md` (autonomous edits to this list are explicitly permitted —
see [MAINTENANCE.md](MAINTENANCE.md)). Record the outcome in `docs/agents/LESSONS.md`.
