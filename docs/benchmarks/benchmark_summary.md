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
| 1 | 922.20 | 895.20 | -27.00 | -2.93% | 2.00 | 1.10 | 4.00 | 4.00 | improved |
| 2 | 1397.30 | 1002.80 | -394.50 | -28.23% | 36.10 | 4.10 | 4.00 | 4.00 | improved |
| 3 | 2163.10 | 1424.80 | -738.30 | -34.13% | 68.40 | 8.70 | 5.60 | 5.00 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 27.60 | 3.40 | 1.61 | 0.54 |
| 2 | 243.92 | 11.71 | 22.96 | 0.83 |
| 3 | 246.57 | 84.01 | 19.19 | 8.14 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 922.20 | 27.60 | 879.00 | 977.00 | 4.00 | 218.40 | 2.00 | 1.61 | 10.70 | 3.20 | 3.00 |
| 2 | 10 | 1397.30 | 243.92 | 1081.00 | 1877.00 | 4.00 | 280.40 | 36.10 | 22.96 | 15.90 | 7.10 | 7.10 |
| 3 | 10 | 2163.10 | 246.57 | 1651.00 | 2464.00 | 5.60 | 410.00 | 68.40 | 19.19 | 23.80 | 10.30 | 10.30 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 895.20 | 3.40 | 893.00 | 901.00 | 4.00 | 202.40 | 1.10 | 0.54 | 10.70 | 3.00 | 3.00 |
| 2 | 10 | 1002.80 | 11.71 | 995.00 | 1033.00 | 4.00 | 210.00 | 4.10 | 0.83 | 15.20 | 7.00 | 7.00 |
| 3 | 10 | 1424.80 | 84.01 | 1353.00 | 1663.00 | 5.00 | 363.00 | 8.70 | 8.14 | 22.30 | 10.50 | 10.20 |

## Current Batches

- Latest original batch: `2026-03-20 18:40:31 [200ef8d-dirty][original]`
- Latest improved batch: `2026-03-20 18:42:10 [200ef8d-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
