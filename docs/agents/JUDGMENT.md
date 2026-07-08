# Externalized Judgment — Rubrics and Checklists

Decision rules that normally require senior judgment, made executable by any model.
Section numbers are referenced from CLAUDE.md and other docs — don't renumber without
updating references (grep for `JUDGMENT.md §`).

Format: each rule has a ✅ example (apply the rule) and a ❌ counterexample (do NOT apply,
or what violating it looks like).

## §1 When to use a stronger model (or escalate)

Escalate per the ladder in [ORCHESTRATION.md](ORCHESTRATION.md) when ANY of:
- A subtask failed acceptance once (haiku) or twice (sonnet).
- The task requires *interpreting* statistics or trading risk, not computing them
  (e.g. "is this drawdown acceptable", "does this p-value justify shipping").
- Two plausible readings of the request lead to materially different work products.
- You are about to touch money-math (`core/simulator.py`, `core/metrics.py`, fee/margin
  logic, options pricing).

✅ Example: a sonnet agent twice produced a fix for `tools/compare.py`'s SH-fetch crash
that broke a different test each time → stop, escalate to opus with both failed diffs and
the test output.
❌ Counterexample: escalating "rename this variable across 4 files" to opus because it
feels safer. Mechanical work with a checkable outcome doesn't need a stronger model — it
needs the test gate.

## §2 When work is genuinely complete

Work is complete when ALL of these are true — otherwise report it as incomplete and say
which item is missing:

1. The originally stated acceptance criteria are met (re-read them before claiming done).
2. `.venv/bin/pytest` passes, IF anything under `core/`, `signals/`, `strategies/`,
   `tools/`, or `tests/` changed.
3. The changed tool/behavior was **actually executed** and its output read — not "should
   work now."
4. Docs updated in their owner file only (ownership table in
   [DIAGNOSIS.md](DIAGNOSIS.md)) — research verdicts in `research/`, tool usage changes in
   `docs/TOOLS.md`.
5. No stray artifacts: charts under `charts/<tool>/`, no leftover scratch files in the
   repo, no accidental edits in `git status` you can't explain.
6. If a mistake was made and corrected along the way, it's recorded in
   [LESSONS.md](LESSONS.md).

✅ Example: fixed the compare.py chart path → ran `.venv/bin/python -m tools.compare SPMO`,
confirmed the PNG landed in `charts/compare/`, ran pytest, updated `docs/TOOLS.md` to
remove the warning, updated the DIAGNOSIS discrepancy list, added a LESSONS entry. Done.
❌ Counterexample: "I've updated the path logic; the chart should now save to
charts/compare/." No execution, no pytest → NOT done, and saying "done" here is a
faithfulness failure, not optimism.

## §3 When to consult Derek (stop and ask; never proceed on these)

- Any edit to `core/portfolio_config.py` or `core/config.py` (except via
  `tools.tune --apply` when Derek asked for a retune).
- Adding/removing a portfolio leg, shipping/retiring an overlay, changing position sizing
  that live tools report.
- Relaxing any validation constraint (the -50% MaxDD limit, `MIN_AVG_ALPHA`, OOS fold
  structure).
- Running `tools.optimize --final` (consumes the annual holdout).
- A golden test fails and the change causing it was *intended* (see §5).
- git push, opening PRs, anything leaving the machine.
- Deleting or overwriting data under `data/`, `research/`, or `docs/archive/`.
- Any "the backtest says we should deploy X" conclusion. Models produce evidence;
  Derek makes deployment decisions.

Also honor his standing preference: when work suggests follow-ups, list them as options and
stop — do not start implementing the next thing without his pick.

✅ Example: `tools.tune` (dry run) shows a Sharpe improvement from new params → present the
comparison table, ask whether to `--apply`. Wait.
❌ Counterexample: asking "should I run pytest?" — no. Iron rule 1 already answers it;
asking delegates *your* checklist to him. Ask about decisions only he can make, not about
following documented rules.

## §4 Signals the current direction is wrong (switch, don't retry)

Any ONE of these means stop retrying the same approach and rethink (or escalate):

- Your second attempt at the same fix failed for the same reason as the first.
- You're about to edit a test's expected values so the test passes (see §5).
- The fix keeps growing special cases (`if ticker == "SMH"` style) instead of shrinking.
- You're fighting the environment rather than the problem — e.g. yfinance/network failures
  in a sandbox (a 403 from the egress proxy is policy, not a bug you can retry away —
  documented in `docs/WORKFLOW.md`).
- The result got *better* than plausible (see §6) after your change.
- You're tuning parameters until the backtest looks good — that's curve-fitting, the exact
  failure mode `tools.optimize`'s OOS discipline exists to prevent.

✅ Example: sector-rotation permutation test came back p=0.000 — implausibly strong. The
right move (which happened, see LESSONS) was to suspect the test harness, and indeed the
null lacked the leverage mechanism. Switch from "interpret result" to "audit the test".
❌ Counterexample: the daily signal tool fails on a network error → "switch approaches" by
writing a synthetic-data fallback that silently returns fake signals. Wrong: for live
tools, loud failure is correct behavior; a quiet plausible-looking wrong answer is the
worst outcome in this repo.

## §5 Minimum quality gates (mechanical, no judgment)

- **Test gate:** `.venv/bin/pytest` after any change to `core/`, `signals/`, `strategies/`,
  `tools/`, or `tests/`. Zero failures required.
- **Golden-test rule:** `tests/` pins exact signal flips and an end-to-end golden backtest
  because real money follows them. If a golden test fails: (a) if the behavior change was
  unintended → your change is wrong, fix the change; (b) if intended → STOP, show Derek the
  before/after numbers and get explicit approval, and only then update the pinned values in
  the same commit as the change, with the reason in the commit message. Never silently
  re-pin.
- **Execution gate:** every touched CLI tool gets run once with realistic args; its output
  (or traceback) goes in the report.
- **Read-back gate:** every file written is re-read from disk (fresh agent or explicit
  re-read) before being reported as written.
- **New-finding gate:** an experiment's verdict may only use the words "validated" or
  "rejected" if it had walk-forward OOS evaluation AND a significance test. Otherwise the
  verdict word is "inconclusive" or "exploratory".

✅ Example: after editing `signals/rsi.py`, pytest runs, and
`tests/test_rsi.py` regression cases pass → gate satisfied.
❌ Counterexample: `python -c "import signals.rsi"` succeeds → gate NOT satisfied; import
success proves nothing about behavior.

## §6 Plausibility ranges (out of range = bug until proven otherwise)

Grounded in this repo's actual 2016–2026 history. When a result lands outside these,
treat it as a harness/annualization/lookahead bug and audit before interpreting:

| Metric | Plausible | Out-of-range examples that were real bugs |
|---|---|---|
| Single-ticker strategy CAGR | -10% … +70% | sector rotation first pass: 900–2300% (monthly data fed to daily annualizer) |
| Core portfolio CAGR | 15% … 45% | — |
| Sharpe | -1.0 … 2.0 | sector rotation first pass: 3–4.6 |
| MaxDD (any 2x-leveraged equity strategy incl. 2020+2022) | -15% … -90% | a leveraged strategy showing a MaxDD *shallower* than -15% (i.e. between 0% and -15%) across 2016–2026 almost certainly has a signal/leverage misalignment (options-*only* strategies showing ~0% MaxDD are a documented legit exception — premium is the max loss) |
| Total fees at $10K capital, 10y | $50 … $500 | — |
| Permutation p-value | ≥ 0.05 has been true for EVERY ticker/strategy tested | the one p=0.000 ever seen was a null-construction bug (see LESSONS) |
| Win rate | 100% = small-sample flag, not confidence (SPMO 9/9 caveat in `research/options_overlay.md`) | — |

Checklist when out of range: (1) frequency mismatch — is a non-daily equity curve hitting
`core/metrics.calc` (assumes 252 periods/yr)? (2) lookahead — does the signal use same-day
close to trade same-day close? (3) null/baseline asymmetry — does the comparison give one
side leverage or fees the other lacks? (4) survivorship — did failed folds get silently
dropped (the `tools.optimize` SKIPPED lesson)?

## §7 Statistical judgment rubric (the taste this repo actually needs)

1. **Read every "alpha" through the leverage-timing lens.** `research/methodology.md` is
   mandatory before interpreting any screener/optimizer output. "Alpha +20%" means "this
   ticker's volatility supports 2x leverage-timing", NOT "the signal has predictive skill".
   ✅ "SOXX shows +19.3% alpha — i.e., strong leverage-carrying capacity; and it fails the
   drawdown constraint, so it's unusable anyway."
   ❌ "SOXX has +19.3% alpha, the signal is great at picking semiconductor entries."
2. **In-sample full-period tables are bait.** Decisions only from walk-forward OOS folds.
   ✅ IWM: +6.4% screener alpha → optimize showed -0.2% OOS → rejected.
   ❌ Sector rotation's first-pass full-period table ("comparable to slightly better than
   SPY") — OOS later showed -6.5%/yr. Quoting the first table as a finding would have been
   wrong.
3. **The null must get the same machinery as the strategy** (leverage, fees, rebalance
   calendar). ✅ The fixed sector-rotation significance test. ❌ p=0.000 from a leveraged
   strategy vs an unleveraged null.
4. **Small samples bound what you may claim.** ~9–13 regimes per ticker: Kelly is
   unreliable (needs 30+ losses), bootstrap CIs of all-positive samples say nothing about
   downside, and "best of 10 candidates" ≠ significant (TLT/FXI).
   ✅ "FXI: +7.0% OOS, p=0.109 — most promising of the batch, not deployable evidence."
   ❌ "FXI works — add it."
5. **Verdict vocabulary is controlled:** `validated` (OOS + significance discipline
   applied, result positive), `rejected` (same discipline, negative), `inconclusive`
   (positive but not significant / insufficient sample), `exploratory` (no OOS yet).
   Anything else ("promising!", "works great") is not a verdict.

## §8 Limits — what this system cannot do (honesty clause)

Decomposition, delegation, checklists, and multi-sample review improve *execution* quality.
They do NOT substitute for judgment on ambiguous or taste-dependent questions. Known cases
in this repo where checklists run out:

- **Risk tolerance and deployment** ("is -41% MaxDD acceptable for +0.1% CAGR?"). No rubric
  answers this. → Always Derek's call (§3).
- **Ambiguous research direction** ("should we explore crypto next?"). → Present evidence +
  options; Derek picks.
- **Novel statistical methodology** (designing a new significance test, choosing a null).
  A wrong-but-plausible design silently corrupts every downstream conclusion. → Use the
  strongest available model, get a second opinion from a fresh-context agent (per
  ORCHESTRATION §Validation), and validate the method on synthetic data with a known
  answer before running it on real data (the pattern `tools.significance` used).
- **Writing quality / doc taste.** A weaker model maintaining these docs should append and
  correct, not restructure (see [MAINTENANCE.md](MAINTENANCE.md)).

When you hit one of these: (1) upgrade to the strongest available model if the question is
analytical; (2) get an independent second opinion if it's methodological; (3) if it's
preference/risk, or the above still disagree — say explicitly: **"this cannot be completed
reliably by this session; it needs Derek / a stronger model"** and record it in
`research/open_questions.md` or the task report. That sentence is a valid, good outcome.
Fabricated confidence is the only unacceptable one.

Uncertainty labeling: facts you verified by execution → state plainly. Facts from docs/memory
not re-verified → "per <file>, unverified". Facts you cannot check → "uncertain". Never
bridge a gap with a plausible guess stated as fact.
