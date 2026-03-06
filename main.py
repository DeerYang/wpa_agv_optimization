"""
根目录兼容入口。

用途：
- 支持直接运行 `python main.py`。
- 自动把 src 目录加入模块搜索路径。
"""

from pathlib import Path
import sys

# 当前文件所在目录即项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent
# src 布局下的源码目录。
SRC_DIR = PROJECT_ROOT / "src"
# 若 src 不在 sys.path，则插入到最前面。
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 导入包内主函数。
from wpa_agv_optimization.main import main


if __name__ == "__main__":
    # 执行主流程。
    main()
