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
| 1 | 2468.90 | 2379.00 | -89.90 | -3.64% | 16.30 | 8.70 | 4.00 | 4.10 | improved |
| 2 | 4260.30 | 3472.10 | -788.20 | -18.50% | 116.60 | 6.30 | 4.00 | 6.10 | improved |
| 3 | 5883.30 | 4601.20 | -1282.10 | -21.79% | 159.30 | 14.00 | 6.00 | 7.60 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 51.97 | 22.35 | 5.02 | 3.20 |
| 2 | 287.59 | 72.39 | 26.42 | 6.07 |
| 3 | 269.65 | 97.54 | 25.32 | 12.91 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2468.90 | 51.97 | 2406.00 | 2604.00 | 4.00 | 227.90 | 16.30 | 5.02 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 4260.30 | 287.59 | 3673.00 | 4697.00 | 4.00 | 237.30 | 116.60 | 26.42 | 135.90 | 131.80 | 131.80 |
| 3 | 10 | 5883.30 | 269.65 | 5505.00 | 6369.00 | 6.00 | 352.30 | 159.30 | 25.32 | 183.60 | 177.20 | 177.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2379.00 | 22.35 | 2358.00 | 2434.00 | 4.10 | 200.30 | 8.70 | 3.20 | 90.00 | 85.90 | 85.90 |
| 2 | 10 | 3472.10 | 72.39 | 3365.00 | 3582.00 | 6.10 | 278.00 | 6.30 | 6.07 | 135.10 | 128.90 | 128.90 |
| 3 | 10 | 4601.20 | 97.54 | 4441.00 | 4786.00 | 7.60 | 359.60 | 14.00 | 12.91 | 180.10 | 172.40 | 172.40 |

## Current Batches

- Latest original batch: `2026-04-02 19:23:40 [frontend-export-refresh][original]`
- Latest improved batch: `2026-04-19 03:12:03 [0b9868b-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
