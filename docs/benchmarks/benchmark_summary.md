# Benchmark Results

## Fixed Protocol

- Main scenarios: `1 2 3`
- Supplementary scenarios: `4 5` (run separately)
- Runs per scenario: `10`
- Base seed: `20260220`
- Metrics: `F / N / D / T / conflict / replan / risk`

## Core Comparison

| Scenario | Original F_mean | Improved F_mean | Delta F | Delta % | Original T_mean | Improved T_mean | Original N_mean | Improved N_mean | Better |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 835.20 | 633.20 | -202.00 | -24.19% | 3.40 | 0.00 | 4.00 | 3.00 | improved |
| 2 | 1046.50 | 1110.90 | 64.40 | 6.15% | 18.60 | 0.10 | 4.00 | 5.00 | original |
| 3 | 1458.30 | 1609.70 | 151.40 | 10.38% | 26.00 | 0.30 | 5.50 | 7.00 | original |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 23.07 | 1.66 | 1.85 | 0.00 |
| 2 | 134.70 | 9.58 | 12.01 | 0.30 |
| 3 | 235.06 | 10.84 | 21.03 | 0.90 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 835.20 | 23.07 | 808.00 | 880.00 | 4.00 | 199.20 | 3.40 | 1.85 | 0.50 | 0.00 | 0.00 |
| 2 | 10 | 1046.50 | 134.70 | 856.00 | 1324.00 | 4.00 | 248.50 | 18.60 | 12.01 | 1.70 | 0.40 | 0.40 |
| 3 | 10 | 1458.30 | 235.06 | 1122.00 | 1849.00 | 5.50 | 361.10 | 26.00 | 21.03 | 2.40 | 0.20 | 0.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 633.20 | 1.66 | 631.00 | 635.00 | 3.00 | 183.20 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 10 | 1110.90 | 9.58 | 1094.00 | 1126.00 | 5.00 | 354.20 | 0.10 | 0.30 | 1.10 | 0.10 | 0.10 |
| 3 | 10 | 1609.70 | 10.84 | 1594.00 | 1622.00 | 7.00 | 531.60 | 0.30 | 0.90 | 4.00 | 0.70 | 0.70 |

## Current Batches

- Latest original batch: `2026-04-22 21:15:38 [8550009-dirty][original]`
- Latest improved batch: `2026-04-24 17:24:10 [541a7a8-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
