# Letter to Future Sessions

Written 2026-07-07 by Claude Fable 5, the last session on this model in this environment.
Everything else in `docs/agents/` is rules; this file is context — the things I'd say to a
colleague taking over.

## Three things Derek never asked about that matter most here

**1. The backtest is systematically optimistic, and the errors all point the same way.**
Individually documented, never added up: (a) the simulator re-levers at every daily close,
so a margin call literally cannot trigger below ~3.33x leverage — real intraday
force-liquidation risk is invisible (`README.md` documents this); (b) the one real
option-chain check ever run found the VIX proxy underpricing QQQ premiums by ~13 IV points
and real spreads 6–43x the assumed cost (`research/options_overlay.md`); (c) the entire
edge is leverage-timing during a decade of mostly-positive drift, with ~9–13 regimes of
history and no ticker clearing p<0.05 (`research/methodology.md`). None of this invalidates
the strategy. It means: expect live results meaningfully below backtest, treat position
sizing (not the signal) as the actual protection, and treat open question #4 (real
execution costs on Futu HK) as the most valuable unfinished work in the repo — more
valuable than any new strategy idea. If Derek asks "what should we work on," that's the
evidence-backed answer.

**2. The most likely real-money incident is operational, not statistical: a silent data
failure.** The daily decision path is `yfinance → cache in data/ → tools.signal → Derek's
margin decision`, and `docs/WORKFLOW.md` documents that several tools exit 0 with "not
enough data" when the fetch fails. In a cron/alert context that's a quiet no-signal or
stale-signal day. yfinance is an unofficial API that breaks periodically. If you ever get
to pick a small engineering task proactively, make data failures loud (non-zero exit or an
explicit `DATA_FETCH_FAILED` marker in the `--alert` JSON) before adding anything new.
Also know: the cache deliberately refetches *full* history because adjusted close rescales
retroactively — do not "optimize" it into tail-appending; that would silently corrupt every
backtest after the next dividend.

**3. The rejections are the asset. Protect the discipline that produced them.** This repo's
real IP is not the SPMO strategy — it's a record of ~40 tested-and-mostly-rejected ideas
under honest validation (walk-forward OOS, significance tests with symmetric nulls,
sensitivity checks). Every time that discipline was skipped, the repo produced a wrong
number that looked great (see `LESSONS.md`, all six seeded entries). The standing
temptation for a future session is to hand Derek a win — a new ticker, a new overlay, a
big CAGR. Resist it: a null result written to `research/` is a fully successful session
here. If you want an evidence-backed "yes" to offer, it already exists: the combined
options overlays (SPMO→QQQ + SMH→SMH, `research/options_overlay.md`) are the strongest
un-deployed edge — sized, sensitivity-checked, bootstrap-CI'd, real-chain-checked. (Be
precise with Derek: under JUDGMENT §7.5's vocabulary they are *not* "validated" — the
walk-forward-OOS + significance bar doesn't apply cleanly to a risk-sized overlay, and no
timing signal in this repo clears p<0.05. They are the most thoroughly stress-tested idea
in the repo, which is a different, honest claim.) Deployment awaits Derek's decision and
the execution-cost work from point 1.

## How this system will most likely degrade

Not by vandalism — by **accretion and drift**. The concrete sequence to expect:

1. A session adds a convenient note to `CLAUDE.md` instead of the owner file. Repeat ×10
   and it's a monolith again (it was 575 lines when I found it).
2. A finding gets restated in a second file "for visibility," the code changes, one copy
   updates — now the repo disagrees with itself and a later session trusts the stale copy
   (this exact thing had already happened by 2026-07-07; see LESSONS entry 6).
3. `docs/agents/ORCHESTRATION.md`'s environment facts (agent types, model names) silently
   expire when the harness changes, and delegation prompts start failing in confusing ways.
4. `LESSONS.md` grows unread. Rules and lessons contradict; nobody consolidates; weaker
   models resolve contradictions arbitrarily and differently each session.

## How to prevent it

- **Respect the ownership table** (`DIAGNOSIS.md`). One fact, one home, links everywhere
  else. This is the single highest-leverage habit.
- **Run the quarterly audit** (`MAINTENANCE.md`) — it's six mechanical checks. Derek:
  saying "run the maintenance audit" once a quarter is the cheapest insurance you can buy.
- **Verify environment facts at the start of delegation-heavy sessions** — the agent/model
  lists in the session's own system-reminder outrank ORCHESTRATION.md.
- **When a rule and reality conflict, reality wins — but the fix is a dated doc edit**, not
  a silent workaround. A workaround teaches nothing to the next session.

## Handoff — open items as of 2026-07-07

- **Unverified discrepancies** (DIAGNOSIS.md bottom): compare.py crash + chart path,
  sizing.py rounding. Found on synthetic data; verify against real code before fixing.
- **README.md is stale** (roadmap section predates 2026-07-06 findings). Needs a
  Derek-approved refresh; it's user-facing.
- **Open research questions:** `research/open_questions.md` items 4, 5, 11, 12, 13, 14.
  Highest value: #4 (real execution). Most fun: #12/#13 (untested options structures) —
  read the spread/covered-call rejections first; the same upside-capping trap applies.
- **Insurance:** if the adversarial review of these docs (closing step of the 2026-07-07
  session) was interrupted or you doubt a doc, run TEMPLATES.md #5 over `docs/agents/` +
  `CLAUDE.md` + `docs/TOOLS.md` with fresh context.

## The honest limits (read JUDGMENT.md §8, but in one line)

Checklists make a Sonnet-class session execute like a careful senior; they do not make it
taste like one. Deployment decisions, risk tolerance, ambiguous direction, and novel
statistical methodology stay with Derek or the strongest model available — and "this can't
be done reliably by this session" is always an acceptable, correct answer.

Good luck. The system works if you read the router and follow the gates. Don't be clever
where a checklist exists; be clever where one doesn't.
