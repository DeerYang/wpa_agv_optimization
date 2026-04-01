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
| 1 | 2372.60 | 2388.40 | 15.80 | 0.67% | 10.00 | 10.20 | 4.00 | 4.00 | original |
| 2 | 3490.90 | 3505.30 | 14.40 | 0.41% | 6.60 | 5.60 | 6.20 | 6.30 | original |
| 3 | 4625.50 | 4716.20 | 90.70 | 1.96% | 14.00 | 20.60 | 7.50 | 7.70 | original |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 15.44 | 13.05 | 1.95 | 2.18 |
| 2 | 54.90 | 49.53 | 5.20 | 4.20 |
| 3 | 105.97 | 78.58 | 9.63 | 8.87 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2372.60 | 15.44 | 2350.00 | 2408.00 | 4.00 | 194.60 | 10.00 | 1.95 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3490.90 | 54.90 | 3410.00 | 3574.00 | 6.20 | 280.50 | 6.60 | 5.20 | 135.00 | 128.80 | 128.80 |
| 3 | 10 | 4625.50 | 105.97 | 4386.00 | 4796.00 | 7.50 | 367.50 | 14.00 | 9.63 | 182.10 | 174.20 | 174.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2388.40 | 13.05 | 2370.00 | 2412.00 | 4.00 | 208.40 | 10.20 | 2.18 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3505.30 | 49.53 | 3444.00 | 3586.00 | 6.30 | 291.20 | 5.60 | 4.20 | 135.00 | 128.70 | 128.70 |
| 3 | 10 | 4716.20 | 78.58 | 4568.00 | 4847.00 | 7.70 | 393.30 | 20.60 | 8.87 | 180.50 | 172.30 | 172.30 |

## Current Batches

- Latest original batch: `2026-04-01 23:07:18 [15a9d56-dirty][original]`
- Latest improved batch: `2026-04-01 23:07:25 [15a9d56-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
