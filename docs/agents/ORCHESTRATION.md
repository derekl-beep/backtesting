# Model Orchestration Guide

How the main session ("commander") should delegate, choose models, and validate work.
Written 2026-07-07 against the environment facts verified below. **Re-verify the facts
section at the start of any session that plans heavy delegation — availability changes.**

## Verified environment facts (as of 2026-07-07 — do not trust from memory)

How to re-verify each fact is noted inline. If reality disagrees with this file, reality
wins; update this file per [MAINTENANCE.md](MAINTENANCE.md).

**Agent types** (listed in the harness `<system-reminder>` at session start — check there):

| subagent_type | Tools | Use for |
|---|---|---|
| `Explore` | no Edit/Write (has Bash — treat as read-only by convention) | fan-out search, "where is X handled", codebase questions |
| `Plan` | no Edit/Write (has Bash — treat as read-only by convention) | designing an implementation plan for a large change |
| `general-purpose` | all tools | multi-step tasks that need edits or command execution |
| `claude` | all tools | catch-all; same capability class as general-purpose |
| `claude-code-guide` | Bash, Read, WebFetch, WebSearch | questions about Claude Code/API/SDK itself |

**Model override** (`model` parameter on the Agent tool): `sonnet`, `opus`, `haiku`
(a `fable` value existed 2026-07-07; assume unavailable after that session — if passing it
errors, fall back to `opus`). If omitted, the subagent inherits the parent model.

**Effort** is a *user-level* setting Derek controls via `/effort`; the current value is
`effortLevel` in `~/.claude/settings.json` (check it — it changes; it flipped from high to
medium within the very session that wrote this file). The Agent tool has **no effort
parameter** — you cannot set effort per-subagent. Do not tell a subagent to "use high
effort"; it's not a knob you hold.

**Continuing an agent:** `SendMessage` with the agent's ID/name continues it with context
intact; a new `Agent` call starts cold. Prefer SendMessage for follow-ups to an agent that
already holds the relevant context.

**Other verified levers:** `run_in_background: true` for parallel long tasks;
`isolation: "worktree"` for edits that shouldn't touch the working tree until accepted.
Skills exist for review workflows: `/code-review` (bug hunt on the current diff),
`/simplify` (quality cleanup), `verify` (run the app to confirm behavior) — check the
session's available-skills list before invoking; never guess a skill name.

**Cost note (honesty):** on this plan, each spawned agent starts cold and re-derives
context — spawning is the expensive path. The thresholds below exist so you delegate when
the *raw material* would pollute the main context, and not otherwise. Delegating a task you
could do with 3 tool calls wastes more than it saves.

## Commander role: synthesize, don't trawl

The main conversation's context is the scarcest resource in a session. Its job is decisions
and synthesis. Concrete thresholds — delegate when a task crosses ANY of these:

| Task | Do it yourself when | Delegate when |
|---|---|---|
| Reading code | ≤ 5 files, or you know exactly which lines | > 5 files, or you'd read whole files to find one thing → `Explore` |
| Searching the repo | 1–2 targeted greps | You can't name the file/symbol and expect > 2 search rounds → `Explore` |
| Web research | Single known URL | Open-ended ("current yfinance rate limits") → `general-purpose` with WebSearch |
| Editing files | ≤ 3 files, non-mechanical | > 3 files of mechanical/repetitive edits → `general-purpose` (haiku/sonnet) |
| Long tool runs | One run you'll read directly | Sweeps producing pages of output → run via Bash with output redirected to a file in the scratchpad, read the summary lines only. (No subagent needed — redirection solves it.) |

What the commander should *never* do: paste a 300-line tool output into its own analysis
when 5 lines carry the conclusion; read all of `research/` "for background" (use the index
`research/README.md`); or spawn a subagent to run a single command.

## Task delegation contract

Every delegation prompt MUST contain these four blocks (templates with placeholders:
[TEMPLATES.md](TEMPLATES.md)):

1. **Objective + why** — one sentence each. The "why" prevents literal-genie failures.
2. **Constraints** — what NOT to touch (e.g. "do not edit `core/portfolio_config.py`",
   "read-only", "do not run `tools.optimize --final`"). Subagents don't inherit CLAUDE.md
   judgment reliably; restate the relevant iron rules.
3. **Acceptance criteria** — checkable, not vibes. "pytest passes and
   `.venv/bin/python -m tools.compare SPMO` exits without traceback", not "works correctly".
4. **Reporting format** — see contract below.

## Reporting contract (for subagents)

- Return **conclusions and `file:line` references only**. No file dumps, no full diffs, no
  raw tool output in the return message.
- Anything longer than ~30 lines goes into a file; return the path. Locations: analysis
  scratch → the session scratchpad dir (shown in the system prompt); durable findings →
  `research/` per the ownership table in [DIAGNOSIS.md](DIAGNOSIS.md).
- Always report: what was checked, what was found, what was NOT checked (explicitly), and
  confidence (confirmed-by-execution vs read-only-inference).
- A subagent's final message is invisible to Derek — the commander must restate anything
  important in its own reply.

## Model selection + escalation/downgrade policy

Default assignments:

| Model | Assign |
|---|---|
| `haiku` | mechanical bulk work with a proven recipe: apply a known pattern across files, format tables, run+collect command outputs |
| `sonnet` | standard implementation, search, research, first-pass review |
| `opus` | debugging that survived one failed attempt, money-math changes, high-stakes review (money-math, statistical verdicts, doc consistency — same rule as [TEMPLATES.md](TEMPLATES.md) #5), anything ambiguous |

Escalation ladder (a *failed attempt* = one delegation whose acceptance criteria were not
met, or where a factual error was found on check):

1. **haiku fails once** on a subtask → re-issue to `sonnet` immediately. Don't retry haiku.
2. **sonnet fails twice** on the *same* subtask (or once, if it had already been escalated
   from haiku) → escalate to `opus`, and include the full failure trace (every attempt's
   prompt, output, and why it failed) in the new prompt. Escalating without the trace
   forfeits the main benefit.
3. **Hard cap: three failed attempts total per subtask across all models** (e.g.
   haiku 1 + sonnet 1 + opus 1, or sonnet 2 + opus 1). After the third: stop, write down
   what was tried, and either consult Derek or record it as cannot-complete-reliably
   (see [JUDGMENT.md](JUDGMENT.md) §8). Endless retries burn the budget and usually signal
   the approach is wrong, not the model.
4. **Downgrade after solving:** once opus/sonnet has produced a working pattern (the fix
   for one instance, the correct recipe), hand *batch application* of that pattern back to
   haiku/sonnet with the pattern pasted verbatim into the prompt.

## Validation is never self-validation

The agent (or session) that produced work does not accept its own work. Concretely:

- **Files/docs written** → a read-back check: a fresh-context agent (or at minimum the
  commander re-reading from disk, not from its own message history) confirms the file
  exists, is complete, and contains no references to files/tools that don't exist.
- **Code changes** → `.venv/bin/pytest` + actually executing the changed tool and reading
  its output. Compile/import success is not acceptance. "The change looks correct" is not
  acceptance.
- **High-risk judgments** (anything touching iron rule 3 in CLAUDE.md, statistical verdicts,
  data-integrity questions) → second opinion: spawn a fresh `general-purpose` (opus) agent
  with the *question and evidence only* — not your conclusion — and compare answers. If they
  disagree, that disagreement goes to Derek, not resolved by picking your own answer.
- **Acceptance prompt for the fresh agent** must include the original acceptance criteria
  verbatim, and ask it to try to *fail* the work, not to confirm it.

## Parallelism

Independent subtasks → issue multiple Agent calls in one message (they run concurrently) or
`run_in_background: true`. Never parallelize two agents editing the same files; use
`isolation: "worktree"` if overlap is possible.
