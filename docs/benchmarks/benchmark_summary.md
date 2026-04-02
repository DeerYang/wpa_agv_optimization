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
| 1 | 2468.90 | 2388.40 | -80.50 | -3.26% | 16.30 | 10.20 | 4.00 | 4.00 | improved |
| 2 | 4260.30 | 3505.30 | -755.00 | -17.72% | 116.60 | 5.60 | 4.00 | 6.30 | improved |
| 3 | 5883.30 | 4716.20 | -1167.10 | -19.84% | 159.30 | 20.60 | 6.00 | 7.70 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 51.97 | 13.05 | 5.02 | 2.18 |
| 2 | 287.59 | 49.53 | 26.42 | 4.20 |
| 3 | 269.65 | 78.58 | 25.32 | 8.87 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2468.90 | 51.97 | 2406.00 | 2604.00 | 4.00 | 227.90 | 16.30 | 5.02 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 4260.30 | 287.59 | 3673.00 | 4697.00 | 4.00 | 237.30 | 116.60 | 26.42 | 135.90 | 131.80 | 131.80 |
| 3 | 10 | 5883.30 | 269.65 | 5505.00 | 6369.00 | 6.00 | 352.30 | 159.30 | 25.32 | 183.60 | 177.20 | 177.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2388.40 | 13.05 | 2370.00 | 2412.00 | 4.00 | 208.40 | 10.20 | 2.18 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3505.30 | 49.53 | 3444.00 | 3586.00 | 6.30 | 291.20 | 5.60 | 4.20 | 135.00 | 128.70 | 128.70 |
| 3 | 10 | 4716.20 | 78.58 | 4568.00 | 4847.00 | 7.70 | 393.30 | 20.60 | 8.87 | 180.50 | 172.30 | 172.30 |

## Current Batches

- Latest original batch: `2026-04-02 18:12:07 [paper-original-oscillation-guard][original]`
- Latest improved batch: `2026-04-02 18:24:05 [paper-original-oscillation-guard][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
