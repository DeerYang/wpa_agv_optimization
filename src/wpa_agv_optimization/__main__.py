"""
包级可执行入口。

支持命令：
- python -m wpa_agv_optimization
"""

from .main import main


if __name__ == "__main__":
    # 直接转发到主入口函数。
    main()
