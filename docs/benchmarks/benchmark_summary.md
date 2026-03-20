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
| 1 | 1116.90 | 1056.70 | -60.20 | -5.39% | 16.00 | 12.30 | 4.00 | 4.00 | improved |
| 2 | 2310.00 | 1239.20 | -1070.80 | -46.35% | 91.00 | 17.80 | 5.30 | 4.00 | improved |
| 3 | 3692.70 | 1800.10 | -1892.60 | -51.25% | 173.30 | 35.80 | 6.90 | 5.10 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 32.17 | 16.52 | 1.95 | 1.73 |
| 2 | 472.23 | 16.09 | 31.30 | 2.44 |
| 3 | 582.30 | 96.97 | 41.98 | 11.23 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 1116.90 | 32.17 | 1066.00 | 1170.00 | 4.00 | 273.10 | 16.00 | 1.95 | 11.20 | 3.00 | 3.00 |
| 2 | 10 | 2310.00 | 472.23 | 1409.00 | 3140.00 | 5.30 | 420.10 | 91.00 | 31.30 | 21.20 | 7.70 | 7.70 |
| 3 | 10 | 3692.70 | 582.30 | 2801.00 | 4472.00 | 6.90 | 627.10 | 173.30 | 41.98 | 31.90 | 13.10 | 13.00 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 1056.70 | 16.52 | 1025.00 | 1074.00 | 4.00 | 251.80 | 12.30 | 1.73 | 11.70 | 2.70 | 2.70 |
| 2 | 10 | 1239.20 | 16.09 | 1218.00 | 1269.00 | 4.00 | 302.00 | 17.80 | 2.44 | 16.40 | 7.20 | 7.20 |
| 3 | 10 | 1800.10 | 96.97 | 1669.00 | 1946.00 | 5.10 | 441.60 | 35.80 | 11.23 | 23.60 | 10.90 | 10.70 |

## Current Batches

- Latest original batch: `2026-03-20 22:35:45 [28d71a7-dirty][original]`
- Latest improved batch: `2026-03-20 22:46:48 [28d71a7-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
