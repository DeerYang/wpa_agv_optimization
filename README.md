# WPA AGV Optimization

基于狼群算法（WPA）的多 AGV 任务分配与路径协同优化项目。

项目面向本科毕业设计场景，核心目标是在 20×20 栅格仓库中，为多台 AGV 分配取货任务并规划无冲突时空路径，同时对 `improved` 与 `original` 两个算法版本做公平 benchmark 对比。

## 项目结构

```text
.
├── src/wpa_agv_optimization/   # Python 主包
├── tests/                      # 单元测试
├── frontend/                   # 前端可视化
├── scripts/                    # benchmark 脚本
├── docs/benchmarks/            # benchmark 历史结果
├── pyproject.toml
└── uv.lock
```

## 环境要求

- Python `>=3.10`
- [uv](https://github.com/astral-sh/uv)

建议先在项目根目录同步依赖：

```bash
uv sync
```

> 本项目后续所有 Python 调用都建议通过 `uv run` 执行，不要直接使用系统 `python` 或 `pytest`。

## 运行项目

### 查看固定场景

```bash
uv run wpa-agv --list-scenarios
```

### 运行改进版算法

```bash
uv run wpa-agv --scenario 1 --seed 42 --algorithm improved
```

### 运行原始版算法

```bash
uv run wpa-agv --scenario 1 --seed 42 --algorithm original
```

### 静默运行

```bash
uv run wpa-agv --scenario 1 --quiet
```

### 包入口方式

```bash
uv run python -m wpa_agv_optimization.main --scenario 1 --algorithm improved
```

## 前端可视化

每次运行后，结果会默认导出到：

- `frontend/data/<algorithm>/result.json`

固定 benchmark 的最佳样例会导出到：

- `frontend/data/improved/scenario-{1,2,3}.json`
- `frontend/data/original/scenario-{1,2,3}.json`

前端页面通过 `fetch` 读取 JSON，因此不要直接双击 `frontend/index.html`。请在项目根目录启动静态服务器：

```bash
uv run python -m http.server 8000 -d frontend
```

然后在浏览器打开：

- [http://localhost:8000](http://localhost:8000)

前端支持：

- 切换 `improved` / `original`
- 查看“最后运行结果”
- 查看固定场景样例
- 回放 AGV 时空路径与收敛曲线

## 测试

### 全量测试

```bash
uv run python -m pytest tests/
```

### 单个测试文件

```bash
uv run python -m pytest tests/test_evaluator_infeasible.py -v
```

### 单个测试方法

```bash
uv run python -m pytest tests/test_wpa_ops.py::RouteAndScoringTests::test_bottleneck_task_ids_picks_worst_agv -v
```

## Benchmark

### 运行改进版 benchmark

```bash
uv run python scripts/run_fixed_benchmarks.py --algorithm improved
```

### 运行原始版 benchmark

```bash
uv run python scripts/run_fixed_benchmarks.py --algorithm original
```

默认 benchmark 协议：

- 主场景：`1 2 3`
- 每场景运行：`10` 次
- 基础种子：`20260220`
- 结果 CSV：`docs/benchmarks/benchmark_runs.csv`
- 汇总 Markdown：`docs/benchmarks/benchmark_summary.md`

## 算法说明

### `improved`

当前项目的改进版 WPA，包含：

- 结构感知候选生成
- 瓶颈任务识别
- 任务风险评分
- Levy flight
- OX 继承与局部修复

### `original`

与论文严格对应的原始版 WPA，采用：

- 连续状态位置向量
- random-key 解码
- 论文式 scouting / summoning / besieging 流程

两个版本共享同一个 `WolfEvaluator`、路径规划器和冲突处理管线，因此 benchmark 对比具有可比性。

## 结果输出

运行完成后，终端会输出：

- 综合适应度 `F`
- 使用车辆数 `N`
- 总行驶距离 `D`
- 时间窗惩罚 `T`
- 冲突 / 死锁 / 重规划 / 改道统计

其中目标函数形式为：

```text
F = W1*D + W2*N + W3*T + W4*C + W5*R + W6*Q + W7*U
```

对应含义：

- `D`：总行驶距离
- `N`：启用车辆数
- `T`：时间窗惩罚
- `C`：冲突处理次数
- `R`：重规划次数
- `Q`：准死锁风险次数
- `U`：未完成任务数

## 说明

- 本项目是纯本地研究工具，不提供网络服务。
- 前端静态服务器只用于本地演示，不建议暴露到公网。
- 如果修改目标函数权重或 benchmark 协议，应同步说明，否则会破坏历史结果可比性。
