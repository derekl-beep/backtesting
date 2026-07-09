# Delegation Prompt Templates

**Read this before reaching for any template below.** These exist for the delegation cases
[ORCHESTRATION.md](ORCHESTRATION.md) actually calls for — a large mechanical sweep, search
in a genuinely unfamiliar area, real independent parallel subtasks. **Most single-feature
work (build X, fix Y, add a test) needs none of these — just do it directly with your own
tools.** Reaching for a template by default, or one-per-file/one-per-persona, is the
token-burning failure mode this system exists to prevent, not a recipe to follow routinely.

Copy the template, fill every `{placeholder}`, delete inapplicable optional lines. Rules
these encode: [ORCHESTRATION.md](ORCHESTRATION.md) (delegation contract, reporting
contract, model ladder). Subagents do not reliably absorb CLAUDE.md — that's why each
template restates the relevant iron rules as constraints. Keep the constraints block even
when it feels redundant.

Model column = starting model; escalate per ORCHESTRATION ladder.

| Template | subagent_type | model | Use when |
|---|---|---|---|
| 1. Search | `Explore` | sonnet (haiku if the question is "where is X defined") | area is genuinely unfamiliar, >2-3 search rounds expected |
| 2. Implementation | `general-purpose` | sonnet (opus if touching money-math) | rare — most implementation is done directly, not delegated |
| 3. Refactoring | `general-purpose` | sonnet; haiku for batch application of a proven pattern | mechanical edits across > 10 files |
| 4. Research / backtest experiment | `general-purpose` | opus preferred, sonnet acceptable | a full research write-up you want out of the main context |
| 5. Review / acceptance | `general-purpose` | opus for money-math, statistical verdicts, or a real-money deployment decision | **not** for routine code review — use the `/code-review` skill inline instead |

---

## 1. Search / codebase question (`Explore`, read-only)

```text
OBJECTIVE: Answer: {question, e.g. "which tools write charts outside charts/<tool>/?"}
WHY: {one sentence, e.g. "auditing the chart-path convention before fixing compare.py"}

SCOPE: Search {dirs, e.g. tools/ core/} in /Users/dereklau/workspace/github/backtesting.
Breadth: {medium | very thorough}.

CONSTRAINTS:
- Read-only. Do not propose edits; report facts.
- Do not read data/ or charts/ contents.

ACCEPTANCE CRITERIA:
- Every claim carries a file:line reference.
- Explicitly list locations you checked that did NOT match (so absence is a finding).

REPORT FORMAT (return message only, no files):
1. Direct answer (≤3 sentences).
2. Evidence: file:line + one-line description per hit.
3. Not checked / uncertain: {list}.
```

## 2. Implementation (`general-purpose`)

```text
OBJECTIVE: {what to build/fix, e.g. "make tools/compare.py handle a failed SH download gracefully"}
WHY: {e.g. "documented crash in docs/WORKFLOW.md; daily-usable tools must fail loudly but cleanly"}

CONTEXT: Repo: /Users/dereklau/workspace/github/backtesting. Read CLAUDE.md first.
Relevant files: {files}. Relevant prior finding: {research/... link or "none"}.

CONSTRAINTS:
- Do NOT edit core/portfolio_config.py, core/config.py, or anything under tests/ unless
  the task says so explicitly.
- Do NOT run `tools.optimize --final` (consumes the annual holdout).
- Match existing code style; simplest change that works; no new abstractions or deps.
- Charts: matplotlib Agg backend, save to charts/<tool>/, plt.close(), never plt.show().
- Run commands as `.venv/bin/python -m tools.<name>` / `.venv/bin/pytest`.

ACCEPTANCE CRITERIA (all required):
- {specific behavior, e.g. "with SH unreachable, compare.py prints 'not enough data' and exits 0-or-documented-nonzero, no traceback"}
- `.venv/bin/pytest` passes with zero failures.
- You executed {command} and its real output demonstrates the criteria.
- If a golden test fails: STOP, do not re-pin values; report the before/after numbers.

REPORT FORMAT:
1. What changed: file:line per edit, one line each.
2. Verification: exact commands run + trimmed real output (≤15 lines each).
3. Anything observed but not fixed (do not fix beyond scope).
4. Confidence: confirmed-by-execution | partially-verified (say which part isn't).
```

## 3. Refactoring (`general-purpose`)

```text
OBJECTIVE: {mechanical change, e.g. "move duplicated iv_proxy logic in {files} to shared helper {location}"}
WHY: {e.g. "three copies have already drifted once"}

PATTERN TO APPLY (follow exactly; if it doesn't fit a case, STOP and report — don't improvise):
{paste the proven pattern/example diff here — mandatory when model=haiku}

CONSTRAINTS:
- Behavior-preserving ONLY. If any test output or tool output changes, you made a mistake.
- No renames/moves beyond the listed files. No "while I'm here" cleanups.
- Do not touch tests/ except imports if a module moved.

ACCEPTANCE CRITERIA (all required):
- `.venv/bin/pytest` passes with zero failures.
- {spot-check command, e.g. ".venv/bin/python -m tools.options_bootstrap GLD"} output is
  identical-in-numbers to the pre-change run (run it BEFORE editing, save output to the
  scratchpad, diff after).
- `git diff --stat` touches only: {expected file list}.

REPORT FORMAT:
1. Files changed + line counts (`git diff --stat` output).
2. Before/after spot-check diff result (must be "identical numbers").
3. Cases where the pattern didn't fit (should be none, else you stopped).
```

## 4. Research / backtest experiment (`general-purpose`)

```text
OBJECTIVE: Test: {hypothesis, e.g. "diagonal spread beats naked ATM call on SPMO→QQQ regimes"}
WHY: {link to research/open_questions.md item #N}

BEFORE STARTING (mandatory, in order):
1. Read research/README.md and check this wasn't already tested. If it was: STOP, report.
2. Read research/methodology.md — interpret every "alpha" as leverage-timing, not skill.
3. Read the plausibility table in docs/agents/JUDGMENT.md §6.

METHOD REQUIREMENTS (a verdict is invalid without these — JUDGMENT.md §5 new-finding gate):
- Walk-forward OOS evaluation (expanding window, same discipline as tools.optimize), never
  a full-period in-sample table alone.
- A significance test where one applies (circular-shift for timing signals; permutation
  with an IDENTICAL-machinery null for selection strategies — null gets the same leverage
  and fees as the strategy).
- Every result checked against the JUDGMENT §6 plausibility ranges; out-of-range = audit
  the harness before interpreting.
- Reuse existing infrastructure (tools/options_backtest.py pricer/regime extractor,
  core/simulator.py, signals/) — do not reimplement money-math that already exists.

CONSTRAINTS:
- Do NOT modify existing strategies/signals/config; new files only, plus (if shipping a
  tool) a new tools/ module.
- Do NOT run tools.optimize --final.
- Verdict vocabulary: validated | rejected | inconclusive | exploratory (JUDGMENT §7.5).

ACCEPTANCE CRITERIA (all required):
- OOS table with per-fold results exists in the write-up.
- Significance p-values reported (or explicit reason why no test applies).
- Write-up appended to the correct research/ file per its README, with date, following the
  existing entry format; research/open_questions.md updated if this closes an item.
- `.venv/bin/pytest` still passes.

REPORT FORMAT (return message):
1. Verdict word + two-sentence summary.
2. Key numbers: OOS avg vs B&H, p-values, MaxDD.
3. Path of the research/ entry written.
4. What was NOT tested (explicit).
Full tables go in the research/ file, not the return message.
```

## 5. Review / acceptance (`general-purpose`, fresh context — reviewer must not be the author)

**Only use this template for the two cases ORCHESTRATION.md's Validation section names:
real-money changes already gated by CLAUDE.md iron rule 3, or novel statistical methodology.
For an ordinary code diff, run the `/code-review` skill inline in the main session instead —
that gets you a second look without spawning and cold-starting another agent.**

```text
OBJECTIVE: Adversarially review {work product: diff | files | research entry}. Your job is
to FAIL it if you can, not to approve it.
WHY: acceptance per docs/agents/ORCHESTRATION.md — authors never self-validate on
real-money or novel-methodology work.

INPUT: {git diff range | file list}. Original acceptance criteria, verbatim:
{paste criteria from the original delegation}

CHECK, IN ORDER:
1. Acceptance criteria: is each one DEMONSTRATED (by execution output), not asserted?
2. Correctness: re-run `.venv/bin/pytest` yourself; re-run {key command} yourself. Do not
   trust pasted output.
3. For research: JUDGMENT.md §6 plausibility ranges; §7 rubric (in-sample trap, null
   symmetry, small-sample overclaim, verdict vocabulary).
4. For docs: every referenced path/tool/command exists (test with ls / --help); no
   contradiction with CLAUDE.md iron rules or the DIAGNOSIS ownership table.
5. Scope: `git diff --stat` contains nothing outside the stated scope.

CONSTRAINTS: read + execute only; do NOT fix anything (report, don't repair).

ACCEPTANCE CRITERIA for YOUR review:
- Every issue: file:line, severity (BLOCKER = criteria unmet or wrong number /
  MAJOR = rule violation / MINOR), and the evidence.
- You state which checks you ran and which you skipped.

REPORT FORMAT:
1. VERDICT: ACCEPT | REJECT (any BLOCKER ⇒ REJECT).
2. Issues, most severe first.
3. Checks performed (commands + result), checks skipped + why.
```
