"""HQAgent-Hub 协议包。

这个文件是**结构性的，不是生成物**——生成器只写 generated/python/ 下的内容。
它存在的理由：没有它时 protocol / protocol.generated 都是 PEP 420 隐式命名空间包，
只在 packages/ 恰好落在 sys.path 上时才成立。pytest 配了 pythonpath 所以测试是绿的，
但进程直接起会 ModuleNotFoundError，装出来的 wheel 也 import 不到
（见 .hqagent/reviews/INT-smoke-W1xW5.md R1）。

另外 PyInstaller 对隐式命名空间包的处理一向不可靠，而一期 Local Hub 要用它打包。
"""

from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent

__all__ = ["PACKAGE_ROOT"]
