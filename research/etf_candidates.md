# ETF candidates

Every ticker screened as a possible addition to the SPMO+GLD portfolio, in reverse
chronological order (newest first). See [methodology.md](methodology.md) before reading
any "alpha" figure below — it's leverage-timing return, not stock-picking skill.

---

## New candidates screened, 2026-07-04

Screened 21 tickers never previously tested in this project, spanning growth/tech-adjacent
sectors, factor/thematic ETFs, metals, commodities, credit, REITs, international/EM, and
crypto — looking for either (a) a genuine SPMO diversifier or (b) another SMH-style case
(margin-blocked but a good options-overlay candidate). None qualify as a portfolio addition;
full results below.

### SOXX — redundant with SMH, not a new diversifier

`tools.screen`: SOXX MA50/100 baseline shows CAGR 53.1%, **alpha +19.3%, Sharpe 1.03** —
nearly as strong as SMH's own numbers. But correlation to SMH is **0.99** — this is the same
semiconductor bet as SMH (different index provider, same underlying exposure), not a
diversifier. `tools.optimize SOXX` hits the identical wall SMH did: 2018-2021 folds pass,
but 2023-2025 are all skipped (`best max_dd -56.3%, needs ≥ -50%`) — blocked from the margin
engine for the same structural reason. `tools.significance SOXX`: p=0.136 (CAGR), p=0.103
(Sharpe) — not significant, consistent with every other ticker tested. `tools.options_backtest
--options-only --ticker SOXX`: works about as well as SMH's overlay (70% win rate, CAGR 15.3%,
Sharpe 1.51, net option P&L +115% on premium) — but since SOXX and SMH are 0.99 correlated,
running both overlays would just double up on the same semiconductor bet, not add a second
independent edge. **Conclusion: skip. If a semiconductor options overlay is wanted, SMH
(already validated, see [options_overlay.md](options_overlay.md)) is the pick — SOXX adds
nothing incremental.**

### XLC, IGV — modest alpha, same drawdown wall as SMH/SOXX

Both are growth/tech-adjacent sector ETFs (Communication Services, Software).
`tools.optimize` on each finds real but modest OOS alpha in the early folds (XLC:
MA50/100, up to +23.8% vs B&H in 2020; IGV: MA20/50, up to +68.2% vs B&H in 2020) but **both
get progressively blocked**: XLC has 3/6 folds skipped from 2023 onward (best training max_dd
-50.8%), IGV has 3/8 folds skipped (best training max_dd -54.1%). Same structural pattern as
SMH/SOXX/TQQQ/UPRO/SOXL: any sufficiently trending, sufficiently volatile equity sector
eventually produces a 2x-leveraged drawdown that breaches the -50% constraint once enough
history accumulates. **Conclusion: rejected for the margin engine.** Not deep-dived for an
options overlay (unlike SOXX, these aren't obviously redundant with an existing pick, but
neither showed alpha strong enough to justify the additional overlay-management overhead
SMH already required) — worth a second look only if the portfolio explicitly wants a third
options-overlay leg.

### COPX (copper miners) — rejected, blocked even earlier than SMH

`tools.screen`: modest alpha (+4.2%) at MA50/100 baseline, and a genuinely different theme
(metals/mining, not tech) — correlation to the existing tech cluster ran 0.43-0.63, the
closest thing to a real diversifier among today's growth-sector candidates. But
`tools.optimize COPX` fails immediately: the 2020 COVID crash alone pushes every param
combo's training-window drawdown past -50% (`best max_dd -53.9%` in the 2020 fold, worsening
to -74.3% by 2021), so **6 of 8 folds are skipped** — worse than SMH, which at least survives
through 2022. **Conclusion: rejected.** Its higher intraday volatility (mining stocks) makes
it hit the margin engine's wall even sooner than the semiconductor names.

### XBI, ARKK, URA, JETS — rejected outright, negative alpha

Screened at MA50/100 baseline alongside the above: XBI (biotech) -4.9% alpha, ARKK
(innovation/growth) -4.2%, URA (uranium) **-17.7%** (uranium's 2023-2025 run was a straight
line up that MA-crossover mostly missed by re-entering late), JETS (airlines) -8.6%. All four
underperform their own buy-and-hold at baseline. Optimization not run — screener alpha this
negative has never turned positive with tuning for any prior candidate in this log.
**Conclusion: rejected.**

### GDX, SLV, DBC, VNQ, HYG, FXI, EWZ — no momentum edge outside growth equities

Screened gold miners (GDX), silver (SLV), broad commodities (DBC), REITs (VNQ), high-yield
credit (HYG), China (FXI), and Brazil (EWZ) at MA50/100 baseline over the full 2016-2026
history:

| Ticker | B&H CAGR | Strat CAGR | Alpha | Sharpe | MaxDD |
|--------|----------|------------|-------|--------|-------|
| GDX | 18.9% | 6.6% | -12.3% | 0.43 | -85.2% |
| SLV | 14.6% | 5.6% | -9.0% | 0.40 | -77.0% |
| DBC | 8.6% | 9.3% | +0.7% | 0.45 | -62.6% |
| VNQ | 6.3% | -1.1% | -7.3% | 0.14 | -67.1% |
| HYG | 5.4% | 3.6% | -1.8% | 0.33 | -36.4% |
| FXI | 1.7% | -1.8% | -3.5% | 0.16 | -77.8% |
| EWZ | 10.7% | -3.5% | -14.2% | 0.21 | -87.9% |

Every one is flat-to-negative alpha. This extends the existing EWJ/EEM/TLT finding (below)
that macro/commodity/credit/EM asset classes don't suit an MA-crossover momentum signal —
now confirmed across metals, broad commodities, REITs, credit, and two country ETFs, not
just Asia-ex-Japan EM and long bonds. **Conclusion: rejected, no further testing.** Would
need a genuinely different (non-MA-crossover) signal family — see Roadmap in CLAUDE.md.

### EFA (developed international) — validated alpha, too correlated to add

`tools.optimize EFA`: MA50/200, **8/8 folds pass** (no drawdown-constraint issue, unlike
every equity-sector candidate above), avg alpha +6.4% across its 3 top-5 appearances.
Genuine, constraint-clean OOS alpha — the first candidate today that isn't blocked by the
drawdown wall. But `tools.screen EFA SPMO GLD` shows correlation to SPMO of **0.70** —
meaningfully correlated, in the same range as MTUM (0.91)/XLK (0.85) that were rejected for
the same reason. `tools.significance EFA`: p=0.208 (CAGR), p=0.161 (Sharpe) — not
significant, same as every other ticker. **Conclusion: rejected for the same reason as
MTUM/XLK below — real alpha, but it concentrates the existing equity-momentum bet rather
than diversifying it.**

### IBIT (bitcoin ETF) — insufficient history, and what there is looks negative

IBIT only began trading January 2024, giving `tools.optimize` exactly **one** OOS fold
(2025). That one fold shows negative alpha across every MA combo tested (-12% to -20% vs
B&H) and two of five combos already breach the -50% drawdown constraint in this single fold.
Correlation to every other ticker screened today is the lowest in the batch (0.19-0.35) —
in principle the best diversification candidate here — but there isn't remotely enough
history to draw a conclusion, and the one fold that exists doesn't help the case.
**Conclusion: not enough data to evaluate. Revisit in a few years once more OOS folds exist;
don't retest sooner.**

### Takeaway from today's batch

Confirms the leverage-timing pattern (see [methodology.md](methodology.md)) generalizes
further than previously shown: **any** trending, high-volatility growth-equity sector
(semis, software, communication services, mining) eventually breaches the margin engine's
drawdown constraint once enough history accumulates — this isn't specific to
semiconductors. And the macro/commodity/credit/international asset classes tested here
(gold miners, silver, broad commodities, REITs, high-yield, China, Brazil, developed
international) show no MA-crossover alpha at all, similar to the EWJ/EEM/TLT/VGT pattern
already established. Nothing found today beats the existing SPMO+GLD construction; SMH
(already validated in [options_overlay.md](options_overlay.md)) remains the strongest
un-deployed edge in this project, reachable only through the bounded-risk options overlay,
not margin.

---

## SMH (semiconductors) — strong momentum alpha, blocked by drawdown constraint, 2026-07-03

**What:** Screened SMH/SOXX (semiconductor sector ETFs) alongside factor ETFs (MTUM, QUAL,
USMV) and sector ETFs (XLK, XLE, XLF, XLV) as untested momentum candidates.

**Screener result (MA50/100 baseline, 2016-2026):** SMH showed the largest alpha of any
ETF tested to date — B&H CAGR 35.8%, strategy CAGR 58.2%, **alpha +22.3%, Sharpe 1.10**
(exceeds SPMO's own 0.94). SOXX nearly identical (+19.3% alpha, 0.99 correlation to SMH —
redundant, pick one). Correlation to SPMO: **0.76** — meaningfully lower than QQQ (0.88) or
MTUM (0.91), i.e. real diversification potential if it clears validation.

**Optimize result:** `tools.optimize SMH` only produces per-fold data through 2022 — 2023,
2024, 2025 silently disappear from the table with no error. Root cause (confirmed by
reproducing `_run_params` directly): the optimizer's training window is *expanding*
(2016 → test_year-1), and SMH's training set crosses a real -60% drawdown once the 2022
chip-sector crash enters it. Because `max_dd` is measured over the whole growing window,
every fold from 2023 onward inherits a training-set max_dd beyond `MAX_DRAWDOWN_LIMIT`
(-50%), so *zero* of the 15 MA combos ever pass the constraint again — for any future year,
permanently. This isn't a math bug (the -50% hard limit is doing exactly what it's supposed
to), but the tool gives no indication why folds vanish; see the tool-improvement note below.

**Does a filter fix the drawdown?** `tools.compare SMH` — tried MA+RSI, MA+MACD, MA+cash
(0x on bearish), MA+SH hedge. None bring MaxDD under -50% (range: -58.8% to -66.4%, vs
SMH's own unleveraged B&H MaxDD of -45.3%). The 2x margin overlay itself is what pushes the
2022 crash past the limit, not a lag in the exit signal — even instant-cash-on-bearish still
breaches it.

**Follow-up: does it work unleveraged? No — rejected, 2026-07-03.** Tested SMH at 1x directly
(`strategies.momentum.positions(sig, leverage=1.0, no_signal_leverage=0.0)` — full exposure
when bullish, cash when bearish, no margin at all). Result: CAGR 25.8%-31.3% across the same
MA candidates, all **below SMH's own B&H CAGR of 35.8%** — negative alpha (-4.5% to -11.9%
full-period). Walk-forward OOS confirms it's not a fluke: every candidate shows **negative
avg OOS alpha (-12.4% to -22.8%) across all 8 folds**, worse than simply holding SMH. The 2x
margin overlay isn't just adding risk on top of a working 1x signal — the 1x signal alone
loses to buy-and-hold. All of SMH's apparent edge lives specifically in the 2x-leverage-
during-confirmed-uptrend mechanism (see [methodology.md](methodology.md)), which is exactly
the mechanism blocked by the drawdown constraint. There is no viable unleveraged path for
SMH.

**Conclusion:** Rejected for the margin engine. SMH has genuinely strong 2x-leveraged
backtest numbers, but (a) the 2x version breaches the drawdown constraint from 2022 onward
and (b) the unleveraged version underperforms simple buy-and-hold. Revisit the margin path
only if the -50% drawdown limit is deliberately relaxed for a small satellite allocation,
understanding that means accepting a real ~-60% peak-to-trough event (2022 was not a
backtest artifact — it happened). **The options-overlay path (bounded risk, no margin) does
work for SMH — see [options_overlay.md](options_overlay.md).**

## MTUM and XLK — validated alpha, too correlated to add, 2026-07-03

**MTUM** (iShares MSCI USA Momentum Factor ETF — a live momentum-factor fund, direct
comparison point for this strategy): `tools.optimize MTUM` → MA30/50, 3/8 folds, avg CAGR
31.7%, avg vs B&H **+13.3%**. Real OOS-validated alpha.

**XLK** (Technology Select Sector SPDR): `tools.optimize XLK` → MA10/100, 5/8 folds, avg
CAGR 35.8%, avg vs B&H **+16.5%**. Also real OOS-validated alpha.

**Why not added:** Correlation to SPMO is 0.91 (MTUM) and 0.85 (XLK) — both move in
lockstep with the existing SPMO leg. Same conclusion as the existing QQQ entry below:
genuine alpha, but adding either would concentrate the equity-momentum bet further rather
than diversify it.

**Conclusion:** Rejected for the current portfolio for the same reason as QQQ. Revisit only
if SPMO is being replaced rather than supplemented.

## QUAL, USMV, XLE, XLF, XLV — rejected at screener, 2026-07-03

Screened alongside MTUM/XLK. All showed flat-to-negative alpha at MA50/100 baseline
(QUAL +2.2%, USMV -0.0%, XLE -5.1%, XLF -0.9%, XLV -6.8%) with Sharpe ≤0.66. Consistent
with the existing EWJ/EEM/TLT/VGT findings: defensive-factor (USMV), value/cyclical-sector
(XLE, XLF), and non-trending (XLV) exposures don't suit an MA-crossover momentum signal.
Optimization not run — screener alpha this weak has never survived OOS validation for any
prior candidate.

**Conclusion:** Confirmed the established pattern. No further testing needed unless a
different (non-MA-crossover) signal family is introduced — see Roadmap in CLAUDE.md.

## Leveraged ETF rotation (TQQQ / UPRO / SOXL) — tested and rejected, 2026-07-03

Closes Roadmap idea #3 ("Leveraged ETF rotation"), previously flagged but never tested.

**What:** Ran `tools.screen` and `tools.optimize` directly on TQQQ (3x QQQ), UPRO (3x SPY),
and SOXL (3x semiconductors) to see if holding them unleveraged (1x, no margin) when bullish
could substitute for this strategy's 2x margin overlay on single-leverage ETFs, avoiding
margin/borrow cost entirely.

**Screener result (MA50/100 baseline):** all three show strongly *negative* alpha vs their
own buy & hold — TQQQ -21.7%, UPRO -18.3%, SOXL **-40.8%** — despite (or because of) huge
absolute returns (SOXL B&H CAGR 57.4%). Classic leveraged-ETF volatility decay: daily
rebalancing inside the fund erodes returns on choppy/whipsaw price action that a slow MA
crossover can't get in and out of fast enough to avoid.

**Optimize result:** none of the 15 MA combos pass the -50% drawdown constraint for TQQQ or
UPRO even in the very first OOS fold (2018) — MaxDD ranges -53% to -74% in that fold alone.
SOXL fails constraints across its entire history ("No results passed constraints").

**Conclusion:** Rejected. A slow MA-crossover trigger is fundamentally incompatible with
3x-leveraged instruments — the whipsaw cost compounds with the fund's own daily-rebalance
decay. Confirms and extends the SPXL/TQQQ finding below (that one tested them as
*additional legs on top of* 2x margin; this one tests them as a full *replacement* for
margin, and the result is the same: leveraged ETFs don't pair with this signal family at
any exposure level). Roadmap item #3 can be closed as tested-and-rejected.

---

## SPXL and TQQQ — rejected 2026-07-01

**What:** Tested adding SPXL (3x S&P500) and TQQQ (3x QQQ) at 5% each, reducing SPMO from 80% to 70%.

**Optimization result:** `python -m tools.optimize SPXL TQQQ` — no param combination passed constraints across any OOS fold (2022-2025). Every combo hit >-50% drawdown or margin calls.

**Why it fails:** Both are already 3x leveraged internally. The strategy adds 2x margin on top when bullish, creating ~6x effective exposure to S&P500/QQQ. Any significant correction produces catastrophic drawdowns before the MA signal flips bearish.

**Portfolio impact (MA50/100, unvalidated):**
| | Old (SPMO 80% + GLD 20%) | New (+SPXL/TQQQ 5% each) |
|---|---|---|
| CAGR | 36.5% | 35.3% |
| Sharpe | 1.14 | 1.00 |
| MaxDD | -33.4% | -44.4% |

Aggregate got worse on every metric. TQQQ strategy CAGR (25.2%) was even below its B&H (35.9%) — the 100-day slow MA is too slow to protect against 3x intraday swings.

**Conclusion:** Internal-leverage ETFs (2x, 3x) are incompatible with this strategy's 2x margin overlay. Stick to single-leverage ETFs and let the strategy provide the leverage.

---

## ETF screener results — 2026-07-01

Common period 2020-01-02 - 2026-07-01, MA50/100 for all (unoptimized).

| Ticker | B&H CAGR | Strat CAGR | Alpha | Sharpe | MaxDD | Corr to SPMO |
|--------|----------|------------|-------|--------|-------|--------------|
| SPMO   | 23.6%    | 38.0%      | +14.3% | 1.07  | -37.7% | 1.00 |
| GLD    | 15.8%    | 27.7%      | +11.9% | 0.92  | -38.9% | 0.16 |
| QQQ    | 21.3%    | 32.8%      | +11.5% | 0.93  | -50.8% | 0.88 |
| VGT    | 23.6%    | 32.7%      | +9.1%  | 0.87  | -53.6% | 0.88 |
| IWM    | 11.0%    | 17.4%      | +6.4%  | 0.60  | -50.0% | 0.75 |
| EEM    | 8.2%     | 14.2%      | +6.0%  | 0.56  | -52.6% | 0.71 |
| EWJ    | 9.4%     | 12.0%      | +2.6%  | 0.52  | -44.0% | 0.67 |
| TLT    | -4.2%    | -9.7%      | -5.4%  | -0.35 | -63.2% | -0.12 |

## QQQ — validated but not added, 2026-07-01

**Optimize result:** MA10/100, 4/4 OOS folds, avg CAGR 24.4%, avg vs B&H +6.3%.

Strong alpha and fully OOS-validated. Not added because correlation to SPMO is 0.88 — it moves in lockstep. Adding QQQ concentrates the equity bet further without diversification benefit. If SPMO turns bearish, QQQ will too.

**Conclusion:** Good ETF on its own, but redundant alongside SPMO. Revisit only if replacing SPMO.

## IWM — screener alpha didn't survive OOS validation, 2026-07-01

**Screener:** +6.4% in-sample alpha looked promising.

**Optimize result:** MA50/100, 4/4 OOS folds — but avg CAGR only 5.0%, avg vs B&H **-0.2%**. Strategy barely keeps pace with IWM buy-and-hold after fees.

**Lesson:** Screener alpha is in-sample (full period). Always run `optimize` before adding — the OOS folds are the real test. IWM's alpha was curve-fitted to the full history, not robust.

**Conclusion:** Rejected. Near-zero OOS alpha doesn't justify the added complexity.

## TLT — rejected at screener, 2026-07-01

Negative alpha (-5.4%), negative Sharpe (-0.35). MA crossover destroys value on bonds — they don't trend the same way equities do. Optimization not needed.

**Conclusion:** Bonds are incompatible with this strategy. Use GLD for the defensive allocation.

## EWJ / EEM — rejected at screener, 2026-07-01

Low alpha (+2.6% / +6.0%), low Sharpe (0.52 / 0.56), MaxDD near the -50% constraint. Macro/sector-rotation ETFs don't trend well on MA crossover signals. Optimization not run.

**Conclusion:** Confirmed the Roadmap note — near-zero alpha. Would need a mean-reversion strategy, not momentum.

## VGT — rejected at screener, 2026-07-01

+9.1% alpha but 0.98 correlation to QQQ and 0.88 to SPMO. Essentially the same bet as QQQ and SPMO. No diversification value.

**Conclusion:** Not worth testing further while SPMO is in the portfolio.
