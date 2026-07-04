# Portfolio construction

## Dynamic GLD allocation — tested, not adopted, 2026-07-01

**Idea:** When SPMO signal is bearish, shift weight from SPMO into GLD (low correlation: 0.16). Three bear configs tested: 60/40, 40/60, 20/80 SPMO/GLD.

**Full-period result (2020-2026):**
| Config | CAGR | Sharpe | MaxDD | vs static |
|--------|------|--------|-------|-----------|
| Static 80/20 | 37.9% | 1.20 | -30.4% | — |
| Dynamic bear 60/40 | 39.3% | 1.24 | -30.3% | +1.4% |
| Dynamic bear 40/60 | 40.3% | 1.25 | -30.3% | +2.5% |
| Dynamic bear 20/80 | 41.0% | 1.22 | -30.3% | +3.1% |

**OOS validation (2022-2026 folds):**
| Fold | Static | Dyn 40/60 |
|------|--------|-----------|
| 2022 | -9.8% | -6.9% ✓ |
| 2023 | 32.0% | 34.5% ✓ |
| 2024 | 88.6% | 88.6% ✓ |
| 2025 | 34.2% | 33.5% ✗ |
| 2026 | 38.9% | 37.3% ✗ |

Win rate: 3/5 folds (60%) across all configs.

**Why the OOS is weak:** The full-period gains concentrate in 2020 (COVID, GLD spiked) and 2022. In 2025-2026 GLD underperformed during SPMO bear periods, so the shift hurt. The improvement is GLD-macro-environment-dependent, not structurally consistent.

**Conclusion:** Not adopted. Fixed 80/20 allocation is simpler and the OOS evidence doesn't justify the operational overhead of rebalancing on signal flips. Revisit if GLD's role in the portfolio changes or a third uncorrelated asset with clearer bear-regime alpha is found.

**Tools added:** `python -m tools.portfolio --dynamic` (full-period comparison), `python -m tools.portfolio --dynamic --oos` (fold-by-fold validation).
