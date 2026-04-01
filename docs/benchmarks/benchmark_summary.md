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
| 1 | 2418.80 | 2388.40 | -30.40 | -1.26% | 11.40 | 10.20 | 4.10 | 4.00 | improved |
| 2 | 3818.70 | 3505.30 | -313.40 | -8.21% | 17.90 | 5.60 | 7.10 | 6.30 | improved |
| 3 | 5361.60 | 4716.20 | -645.40 | -12.04% | 60.10 | 20.60 | 8.30 | 7.70 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 41.85 | 13.05 | 3.07 | 2.18 |
| 2 | 58.55 | 49.53 | 11.61 | 4.20 |
| 3 | 203.67 | 78.58 | 21.65 | 8.87 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2418.80 | 41.85 | 2370.00 | 2526.00 | 4.10 | 213.10 | 11.40 | 3.07 | 90.00 | 85.90 | 85.90 |
| 2 | 10 | 3818.70 | 58.55 | 3751.00 | 3932.00 | 7.10 | 356.70 | 17.90 | 11.61 | 135.90 | 128.80 | 128.80 |
| 3 | 10 | 5361.60 | 203.67 | 5020.00 | 5650.00 | 8.30 | 453.30 | 60.10 | 21.65 | 187.40 | 177.90 | 177.90 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2388.40 | 13.05 | 2370.00 | 2412.00 | 4.00 | 208.40 | 10.20 | 2.18 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3505.30 | 49.53 | 3444.00 | 3586.00 | 6.30 | 291.20 | 5.60 | 4.20 | 135.00 | 128.70 | 128.70 |
| 3 | 10 | 4716.20 | 78.58 | 4568.00 | 4847.00 | 7.70 | 393.30 | 20.60 | 8.87 | 180.50 | 172.30 | 172.30 |

## Current Batches

- Latest original batch: `2026-04-01 22:22:34 [f98912b-dirty][original]`
- Latest improved batch: `2026-04-01 22:21:01 [f98912b-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
