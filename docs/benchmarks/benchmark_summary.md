# Benchmark Results

## Fixed Protocol

- Main scenarios: `1 2 3`
- Supplementary scenarios: `4 5` (run separately)
- Runs per scenario: `10`
- Base seed: `20260220`
- Metrics: `F / N / D / T / conflict / replan / risk`

## Core Comparison

| Scenario | Original F_mean | Improved F_mean |  Delta F | Delta % | Original T_mean | Improved T_mean | Original N_mean | Improved N_mean | Better   |
| -------- | --------------: | --------------: | -------: | ------: | --------------: | --------------: | --------------: | --------------: | -------- |
| 1        |         2468.90 |         2380.90 |   -88.00 |  -3.56% |           16.30 |            9.30 |            4.00 |            4.10 | improved |
| 2        |         4260.30 |         3456.10 |  -804.20 | -18.88% |          116.60 |            6.80 |            4.00 |            6.00 | improved |
| 3        |         5883.30 |         4577.40 | -1305.90 | -22.20% |          159.30 |            6.70 |            6.00 |            7.80 | improved |

## Stability

| Scenario | Original F_std | Improved F_std | Original T_std | Improved T_std |
| -------- | -------------: | -------------: | -------------: | -------------: |
| 1        |          51.97 |          22.63 |           5.02 |           3.38 |
| 2        |         287.59 |          80.73 |          26.42 |           5.72 |
| 3        |         269.65 |          94.09 |          25.32 |           5.76 |

## Original Summary

| Scenario | Runs |  F_Mean |  F_Std |   F_Min |   F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
| -------- | ---: | ------: | -----: | ------: | ------: | -----: | -----: | -----: | ----: | ------------: | ----------: | --------: |
| 1        |   10 | 2468.90 |  51.97 | 2406.00 | 2604.00 |   4.00 | 227.90 |  16.30 |  5.02 |         90.00 |       86.00 |     86.00 |
| 2        |   10 | 4260.30 | 287.59 | 3673.00 | 4697.00 |   4.00 | 237.30 | 116.60 | 26.42 |        135.90 |      131.80 |    131.80 |
| 3        |   10 | 5883.30 | 269.65 | 5505.00 | 6369.00 |   6.00 | 352.30 | 159.30 | 25.32 |        183.60 |      177.20 |    177.20 |

## Improved Summary

| Scenario | Runs |  F_Mean | F_Std |   F_Min |   F_Max | N_Mean | D_Mean | T_Mean | T_Std | Conflict_Mean | Replan_Mean | Risk_Mean |
| -------- | ---: | ------: | ----: | ------: | ------: | -----: | -----: | -----: | ----: | ------------: | ----------: | --------: |
| 1        |   10 | 2380.90 | 22.63 | 2350.00 | 2438.00 |   4.10 | 196.20 |   9.30 |  3.38 |         90.00 |       85.90 |     85.90 |
| 2        |   10 | 3456.10 | 80.73 | 3299.00 | 3576.00 |   6.00 | 271.10 |   6.80 |  5.72 |        135.00 |      129.00 |    129.00 |
| 3        |   10 | 4577.40 | 94.09 | 4427.00 | 4729.00 |   7.80 | 367.80 |   6.70 |  5.76 |        180.90 |      173.00 |    173.00 |

## Current Batches

- Latest original batch: `2026-04-02 19:23:40 [frontend-export-refresh][original]`
- Latest improved batch: `2026-04-06 21:32:14 [6c002b2-dirty][improved]`
- Raw rows file: `docs/benchmarks/benchmark_runs.csv`
