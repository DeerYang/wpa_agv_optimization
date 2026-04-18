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
| 1 | 2468.90 | 2380.10 | -88.80 | -3.60% | 16.30 | 10.10 | 4.00 | 4.00 | improved |
| 2 | 4260.30 | 3477.10 | -783.20 | -18.38% | 116.60 | 4.10 | 4.00 | 6.30 | improved |
| 3 | 5883.30 | 4598.90 | -1284.40 | -21.83% | 159.30 | 10.80 | 6.00 | 7.80 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 51.97 | 16.65 | 5.02 | 1.92 |
| 2 | 287.59 | 60.70 | 26.42 | 4.06 |
| 3 | 269.65 | 82.62 | 25.32 | 5.74 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2468.90 | 51.97 | 2406.00 | 2604.00 | 4.00 | 227.90 | 16.30 | 5.02 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 4260.30 | 287.59 | 3673.00 | 4697.00 | 4.00 | 237.30 | 116.60 | 26.42 | 135.90 | 131.80 | 131.80 |
| 3 | 10 | 5883.30 | 269.65 | 5505.00 | 6369.00 | 6.00 | 352.30 | 159.30 | 25.32 | 183.60 | 177.20 | 177.20 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2380.10 | 16.65 | 2350.00 | 2406.00 | 4.00 | 201.10 | 10.10 | 1.92 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3477.10 | 60.70 | 3375.00 | 3560.00 | 6.30 | 278.00 | 4.10 | 4.06 | 135.00 | 128.70 | 128.70 |
| 3 | 10 | 4598.90 | 82.62 | 4465.00 | 4750.00 | 7.80 | 362.30 | 10.80 | 5.74 | 180.00 | 172.20 | 172.20 |

## Current Batches

- Latest original batch: `2026-04-02 19:23:40 [frontend-export-refresh][original]`
- Latest improved batch: `2026-04-19 03:34:15 [a5515aa-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
