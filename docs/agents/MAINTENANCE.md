# Maintenance Protocol for the Agent-System Docs

How future sessions keep `CLAUDE.md`, `docs/`, and `research/` accurate without degrading
them. The failure mode to prevent is drift + bloat, not vandalism (see
[LETTER.md](LETTER.md)).

## Edit permissions

| File | Autonomous edits allowed | Notes |
|---|---|---|
| `docs/agents/LESSONS.md` | ✅ append entries; consolidation per trigger below | The designated place to write after any mistake |
| `research/*.md` | ✅ append findings; fix factual errors | Follow each file's existing entry format; never delete a verdict — supersede it with a dated correction (see the strikethrough pattern in `research/signal_configs.md`) |
| `research/open_questions.md` | ✅ add items; mark items done with date + link | |
| `docs/TOOLS.md` | ✅ update command docs when the tool itself changed; ✅ fix checkably wrong claims (wrong path/flag/filename) found in an audit | Feature docs change alongside the code change that makes them true |
| `docs/agents/ORCHESTRATION.md` "Verified environment facts" section | ✅ update when reality disagrees | Re-verify before editing; date the change |
| `docs/WORKFLOW.md` | ✅ update bug table when a listed bug is fixed/refuted | Keep in sync with DIAGNOSIS discrepancy list |
| `CLAUDE.md` | ⚠ Derek's approval required | Highest blast radius — every session loads it. Propose the diff, wait |
| `docs/agents/DIAGNOSIS.md` "Known discrepancies" list | ✅ update entries with verified fix/refute outcomes (this is required upkeep, not policy) | Keep in sync with `docs/WORKFLOW.md` |
| `docs/agents/DIAGNOSIS.md` (rest), `JUDGMENT.md`, `TEMPLATES.md`, `MAINTENANCE.md`, `LETTER.md` | ⚠ Derek's approval for policy changes; ✅ autonomous for factual corrections (a claim that is checkably false: broken path, renamed tool, dead link, wrong count) | Changing a threshold/rule/permission = policy |
| `docs/archive/*` | ❌ never edit or delete | Point-in-time backups |
| `README.md` | ⚠ Derek's approval | User-facing; known stale as of 2026-07-07 (roadmap section) |

When in doubt whether an edit is "factual" or "policy": it's policy — ask.

## Recording lessons (mandatory after any mistake)

A "mistake" = wrong output caught by a gate, a reviewer, Derek, or reality (not: a typo you
fixed before running anything). Append to [LESSONS.md](LESSONS.md) in this exact format:

```markdown
## YYYY-MM-DD — <one-line title>
- **What happened:** <2-3 sentences, concrete>
- **Wrong belief:** <the assumption that caused it>
- **Correction:** <what's true instead>
- **Rule change:** <none | link to the doc edit made because of this>
```

Keep entries ≤ 10 lines. If the lesson invalidates something in another doc, fix that doc
(within permissions above) and link it — a lesson that contradicts a live rule but doesn't
change it is a drift seed.

## Consolidation triggers (do these when the condition hits, not on a calendar)

| Trigger | Action |
|---|---|
| `CLAUDE.md` > 150 lines | Propose (to Derek) moving content out to owner files; CLAUDE.md holds invariants + routing only |
| `LESSONS.md` > 25 entries | Consolidate: promote recurring lessons into a rule in JUDGMENT.md (approval path), archive superseded entries to `docs/archive/` |
| A `research/` topic file > ~500 lines | Split by sub-topic, update `research/README.md` index (the 2026-07-04 split of RESEARCH.md is the precedent) |
| Same question answered twice from scratch in different sessions | The answer wasn't findable — improve the routing (CLAUDE.md table or research/README.md index) |

## Quarterly audit (any session may run this when Derek asks for "maintenance")

1. `wc -l CLAUDE.md` — over 150 → consolidation trigger.
2. Link check: verify every path referenced in `CLAUDE.md`, `docs/TOOLS.md`, and
   `docs/agents/*.md` exists (`ls` each; grep for `\.md` references).
3. Drift check: compare the portfolio params stated anywhere in docs against
   `core/portfolio_config.py` (the truth). Fix docs, never code, on mismatch.
4. Discrepancy list in [DIAGNOSIS.md](DIAGNOSIS.md): any item now fixed/refuted → update
   it and `docs/WORKFLOW.md`.
5. Environment facts in [ORCHESTRATION.md](ORCHESTRATION.md): still match the session's
   actual agent/model/skill lists?
6. Report findings; apply only edits permitted above.

## Rules for editing these docs at all (any model)

- One edit, one purpose. Don't restructure while fixing a fact.
- Preserve section numbers in JUDGMENT.md (they're referenced by `§N` elsewhere — grep
  `JUDGMENT.md §` before renumbering).
- Every rule you add needs: a checkable condition, an example, a counterexample. If you
  can't produce all three, it's not ready to be a rule — put it in LESSONS.md instead.
- Never delete a rule you disagree with — propose the deletion to Derek with the reason.
