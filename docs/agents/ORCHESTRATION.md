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
context — spawning is the expensive path, not the safe default. Every one of these docs
being read at session start is itself a cost; loading a subagent to redo work the commander
could do directly compounds it. The single most common way this system burns a session's
budget is spawning several agents to build one ordinary feature. Default to zero subagents
per task; the thresholds below exist for the real exceptions, not as a menu to reach for.

## Commander role: synthesize, don't trawl

The main conversation's context is the scarcest resource in a session. Its job is decisions
and synthesis. A task spanning several files or several steps is still **one task** —
"implement feature X" is not four subtasks for four subagents just because it touches four
files. Delegate only when a task crosses ANY of these (deliberately strict) thresholds:

| Task | Do it yourself when | Delegate when |
|---|---|---|
| Reading code | Nearly always — Read/Grep/Glob are cheaper than a cold subagent for anything ≤ ~15 files | The area is genuinely unfamiliar and you can't even guess where to look after 2–3 search rounds → `Explore` |
| Searching the repo | Nearly always — a few targeted greps | Same bar as above; "I could grep it in 2 tries" is not a delegation case |
| Web research | Single known URL, or one WebSearch call | Genuinely open-ended research spanning many searches that would flood the main context → `general-purpose` with WebSearch |
| Editing files | Default — implement the feature/fix yourself, however many files it touches | Only mechanical, repetitive edits with a proven pattern across > 10 files → `general-purpose` (haiku for the batch apply) |
| Long tool runs | One run you'll read directly, or redirect output to a scratchpad file and read the summary | Essentially never needs a subagent — redirection solves it |

What the commander should *never* do: paste a 300-line tool output into its own analysis
when 5 lines carry the conclusion; read all of `research/` "for background" (use the index
`research/README.md`); spawn a subagent to run a single command; spawn one agent per file or
per step of a feature you could build directly; or spawn a "review"/"second opinion" agent
for routine work that isn't money-math, a real-money deployment decision, or novel
statistical methodology (see Validation below — that list is short on purpose).

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

## Validation is never self-validation — but "validation" usually means re-checking
## yourself, not spawning another agent

Verifying work you just did means re-reading it from disk and re-running it, not
necessarily handing it to a second agent. Concretely:

- **Files/docs written** → re-read the file from disk yourself (not from memory of writing
  it) and confirm it exists, is complete, and contains no references to files/tools that
  don't exist. No subagent needed for this — it's one Read call.
- **Code changes** → `.venv/bin/pytest` + actually executing the changed tool and reading
  its output, yourself. Compile/import success is not acceptance. "The change looks correct"
  is not acceptance. Still no subagent needed.
- **Only these two cases** warrant a fresh-context second opinion, because the cost of being
  wrong is asymmetric enough to justify it: (a) anything already gated by CLAUDE.md iron rule
  3 (real-money changes needing Derek's yes anyway), and (b) designing genuinely novel
  statistical methodology (JUDGMENT.md §8) where a wrong-but-plausible design silently
  corrupts every downstream conclusion. For these two, spawn one fresh `general-purpose`
  (opus) agent with the *question and evidence only* — not your conclusion. If it disagrees,
  that goes to Derek, not resolved by picking your own answer.
- Routine feature work, ordinary bug fixes, doc updates, and research write-ups do **not**
  get a second-opinion agent — the test gate + execution gate + your own read-back is the
  acceptance bar. If you want a lightweight second look on a diff, use the `/code-review` or
  `/simplify` skill inline in the main session; that is not the same as spawning an agent.
- **Acceptance prompt for the fresh agent**, when one of the two cases above actually
  applies, must include the original acceptance criteria verbatim, and ask it to try to
  *fail* the work, not to confirm it.

## Parallelism

Default is still zero subagents for a normal feature build. When a session does have
genuinely independent delegated subtasks (per the thresholds above), issue multiple Agent
calls in one message (they run concurrently) or `run_in_background: true`. Never parallelize
two agents editing the same files; use `isolation: "worktree"` if overlap is possible. Do
not spawn a "team" of agents (e.g. one per persona, one per file) for a task one session can
just think through and build directly — that pattern is exactly what burns the budget.
