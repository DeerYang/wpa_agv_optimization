# WPA AGV Optimization

多 AGV 调度与路径协同优化项目。

## 运行项目

建议直接使用仓库里的虚拟环境：

```powershell
.\.venv\Scripts\python.exe main.py --list-scenarios
```

运行一个固定场景示例：

```powershell
.\.venv\Scripts\python.exe main.py --scenario 1 --algorithm improved
```

可选参数：

- `--scenario`：固定场景编号
- `--algorithm improved|original`：选择改进算法或原始算法
- `--seed`：固定随机种子，便于复现
- `--quiet`：静默运行，只输出最终结果

如果希望通过包入口运行，也可以先安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

然后执行：

```powershell
.\.venv\Scripts\python.exe -m wpa_agv_optimization.main --scenario 1 --algorithm improved
```

或者直接使用安装后的命令：

```powershell
wpa-agv --scenario 1 --algorithm improved
```

## 查看前端结果

算法运行后会把结果导出到 `frontend/data/` 下，前端默认从这些 JSON 文件读取结果。

不要直接双击 `frontend/index.html`，因为页面会通过 `fetch` 加载数据。  
请在项目根目录启动一个本地静态服务器，例如：

```powershell
.\.venv\Scripts\python.exe -m http.server 8000 -d frontend
```

然后在浏览器打开：

- [http://localhost:8000](http://localhost:8000)

前端页面中可以：

- 选择算法版本
- 查看“最后运行结果”
- 查看各场景示例结果
