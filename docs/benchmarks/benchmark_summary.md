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
| 1 | 835.20 | 808.80 | -26.40 | -3.16% | 3.40 | 2.00 | 4.00 | 4.00 | improved |
| 2 | 1046.50 | 804.80 | -241.70 | -23.10% | 18.60 | 1.30 | 4.00 | 4.00 | improved |
| 3 | 1458.30 | 1023.70 | -434.60 | -29.80% | 26.00 | 0.10 | 5.50 | 5.00 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 23.07 | 4.40 | 1.85 | 0.00 |
| 2 | 134.70 | 8.48 | 12.01 | 0.46 |
| 3 | 235.06 | 13.72 | 21.03 | 0.30 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 835.20 | 23.07 | 808.00 | 880.00 | 4.00 | 199.20 | 3.40 | 1.85 | 0.50 | 0.00 | 0.00 |
| 2 | 10 | 1046.50 | 134.70 | 856.00 | 1324.00 | 4.00 | 248.50 | 18.60 | 12.01 | 1.70 | 0.40 | 0.40 |
| 3 | 10 | 1458.30 | 235.06 | 1122.00 | 1849.00 | 5.50 | 361.10 | 26.00 | 21.03 | 2.40 | 0.20 | 0.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 808.80 | 4.40 | 802.00 | 814.00 | 4.00 | 188.00 | 2.00 | 0.00 | 0.20 | 0.00 | 0.00 |
| 2 | 10 | 804.80 | 8.48 | 795.00 | 824.00 | 4.00 | 190.20 | 1.30 | 0.46 | 0.40 | 0.00 | 0.00 |
| 3 | 10 | 1023.70 | 13.72 | 1004.00 | 1043.00 | 5.00 | 267.50 | 0.10 | 0.30 | 1.30 | 0.00 | 0.00 |

## Current Batches

- Latest original batch: `2026-04-22 21:15:38 [8550009-dirty][original]`
- Latest improved batch: `2026-04-22 21:05:06 [8550009-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
