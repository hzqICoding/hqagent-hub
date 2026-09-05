# HQAgent Local Hub

Local Hub 是桌面前端唯一连接的本机服务。本包负责进程生命周期、SQLite、事务事件、HTTP/WS 鉴权、Update Agent 代理和升级排空；Agent 适配、角色解析与工作流编排由 Port 注入。

## 开发运行

```powershell
cd apps/hub
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m runtime.main
```

运行数据默认写入 `%LOCALAPPDATA%\HQAgent-Hub\`。测试可通过 `HQAGENT_HUB_DATA_DIR` 指向临时目录。

## 验证

```powershell
pytest apps/hub/tests -q
```

