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
| 1 | 2395.60 | 2389.10 | -6.50 | -0.27% | 8.20 | 10.90 | 4.10 | 4.00 | improved |
| 2 | 3949.20 | 3560.10 | -389.10 | -9.85% | 34.20 | 12.90 | 6.80 | 6.10 | improved |
| 3 | 5708.20 | 4796.30 | -911.90 | -15.98% | 92.70 | 18.50 | 8.40 | 8.40 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
|---|---:|---:|---:|---:|
| 1 | 24.17 | 19.00 | 3.49 | 1.22 |
| 2 | 114.69 | 55.23 | 15.36 | 5.34 |
| 3 | 195.77 | 126.57 | 18.04 | 12.48 |

## Original Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2395.60 | 24.17 | 2370.00 | 2449.00 | 4.10 | 221.90 | 8.20 | 3.49 | 90.00 | 85.90 | 85.90 |
| 2 | 10 | 3949.20 | 114.69 | 3716.00 | 4135.00 | 6.80 | 352.60 | 34.20 | 15.36 | 136.80 | 129.80 | 129.80 |
| 3 | 10 | 5708.20 | 195.77 | 5394.00 | 5966.00 | 8.40 | 458.40 | 92.70 | 18.04 | 187.20 | 178.00 | 178.00 |

## Improved Summary

| Scenario | Runs | F_Mean | F_Std | F_Min | F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 2389.10 | 19.00 | 2366.00 | 2424.00 | 4.00 | 202.10 | 10.90 | 1.22 | 90.00 | 86.00 | 86.00 |
| 2 | 10 | 3560.10 | 55.23 | 3483.00 | 3642.00 | 6.10 | 286.40 | 12.90 | 5.34 | 135.90 | 129.70 | 129.70 |
| 3 | 10 | 4796.30 | 126.57 | 4595.00 | 5062.00 | 8.40 | 400.50 | 18.50 | 12.48 | 180.00 | 171.60 | 171.60 |

## Current Batches

- Latest original batch: `2026-04-01 21:52:59 [b064168-dirty][original]`
- Latest improved batch: `2026-04-01 21:47:55 [b064168-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
