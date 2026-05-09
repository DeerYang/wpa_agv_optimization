# Benchmark Results

## Fixed Protocol

- Main scenarios: `1 2 3`
- Runs per scenario: `10`
- Base seed: `20260220`
- Metrics: `F / N / D / T / conflict / replan / risk`

## Core Comparison

| Scenario | Original F_mean | Improved F_mean | Delta F | Delta % | Original T_mean | Improved T_mean | Original N_mean | Improved N_mean | Better |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 663.40 | 633.20 | -30.20 | -4.55% | 0.00 | 0.00 | 3.00 | 3.00 | improved |
| 2 | 1694.60 | 1109.30 | -585.30 | -34.54% | 44.50 | 0.10 | 5.00 | 5.00 | improved |
| 3 | 3081.10 | 1623.30 | -1457.80 | -47.31% | 104.60 | 1.30 | 8.10 | 7.00 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 9.29 | 1.66 | 0.00 | 0.00 |
| 2 | 186.24 | 8.44 | 17.37 | 0.30 |
| 3 | 469.72 | 30.99 | 42.36 | 2.24 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 663.40 | 9.29 | 643.00 | 675.00 | 3.00 | 211.40 | 0.00 | 0.00 | 0.50 | 0.00 | 0.00 |
| 2 | 10 | 1694.60 | 186.24 | 1384.00 | 1983.00 | 5.00 | 441.80 | 44.50 | 17.37 | 6.00 | 2.60 | 2.60 |
| 3 | 10 | 3081.10 | 469.72 | 2596.00 | 3996.00 | 8.10 | 715.00 | 104.60 | 42.36 | 11.00 | 4.70 | 4.70 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 633.20 | 1.66 | 631.00 | 635.00 | 3.00 | 183.20 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 10 | 1109.30 | 8.44 | 1094.00 | 1126.00 | 5.00 | 353.40 | 0.10 | 0.30 | 0.90 | 0.10 | 0.10 |
| 3 | 10 | 1623.30 | 30.99 | 1591.00 | 1696.00 | 7.00 | 538.60 | 1.30 | 2.24 | 3.80 | 0.50 | 0.50 |

## GA Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 645.60 | 5.37 | 639.00 | 659.00 | 3.00 | 195.60 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| 2 | 10 | 1361.00 | 69.33 | 1235.00 | 1472.00 | 5.00 | 406.20 | 16.00 | 6.94 | 4.70 | 2.00 | 2.00 |
| 3 | 10 | 2613.10 | 204.51 | 2274.00 | 2912.00 | 8.00 | 693.40 | 64.60 | 20.30 | 7.70 | 3.30 | 3.30 |

## SA Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 668.40 | 11.21 | 645.00 | 681.00 | 3.00 | 216.00 | 0.00 | 0.00 | 0.60 | 0.00 | 0.00 |
| 2 | 10 | 1526.60 | 199.16 | 1236.00 | 1901.00 | 5.00 | 411.80 | 33.10 | 16.88 | 3.90 | 1.40 | 1.40 |
| 3 | 10 | 3016.50 | 282.65 | 2569.00 | 3329.00 | 8.00 | 717.40 | 101.90 | 26.65 | 8.00 | 3.70 | 3.70 |

## Current Batches

- Latest original batch: `2026-04-24 23:44:17 [46c9f27-dirty][original]`
- Latest improved batch: `2026-04-24 23:58:24 [46c9f27-dirty][improved]`
- Latest ga batch: `2026-05-09 22:38:20 [8105e2e-dirty][ga]`
- Latest sa batch: `2026-05-09 22:38:06 [8105e2e-dirty][sa]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
