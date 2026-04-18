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
| 1 | 2502.50 | 2380.10 | -122.40 | -4.89% | 20.10 | 10.10 | 4.00 | 4.00 | improved |
| 2 | 4378.30 | 3477.10 | -901.20 | -20.58% | 129.60 | 4.10 | 4.00 | 6.30 | improved |
| 3 | 5886.80 | 4598.90 | -1287.90 | -21.88% | 157.70 | 10.80 | 5.90 | 7.80 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 68.18 | 16.65 | 6.27 | 1.92 |
| 2 | 176.55 | 60.70 | 16.95 | 4.06 |
| 3 | 349.03 | 82.62 | 32.98 | 5.74 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2502.50 | 68.18 | 2408.00 | 2580.00 | 4.00 | 223.50 | 20.10 | 6.27 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 4378.30 | 176.55 | 4139.00 | 4697.00 | 4.00 | 239.30 | 129.60 | 16.95 | 135.00 | 131.00 | 131.00 |
| 3 | 10 | 5886.80 | 349.03 | 5404.00 | 6489.00 | 5.90 | 354.50 | 157.70 | 32.98 | 185.50 | 179.10 | 179.10 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2380.10 | 16.65 | 2350.00 | 2406.00 | 4.00 | 201.10 | 10.10 | 1.92 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3477.10 | 60.70 | 3375.00 | 3560.00 | 6.30 | 278.00 | 4.10 | 4.06 | 135.00 | 128.70 | 128.70 |
| 3 | 10 | 4598.90 | 82.62 | 4465.00 | 4750.00 | 7.80 | 362.30 | 10.80 | 5.74 | 180.00 | 172.20 | 172.20 |

## Current Batches

- Latest original batch: `2026-04-19 04:07:41 [d266e8c-dirty][original]`
- Latest improved batch: `2026-04-19 04:04:36 [d266e8c-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
