# HQAgent Update Agent

独立常驻 Go 进程，窗口关闭不会中止后台下载。Vue 只使用 Local Hub。
本模块的 `product` package 同时供独立 Updater 使用，避免两处重复产品策略或手写协议 DTO。

```powershell
go -C apps/update-agent test ./...
go -C apps/update-agent build -o E:/tmp/hqagent-update-agent.exe ./cmd/hqagent-update-agent
```

运行时安装目录固定 `%LOCALAPPDATA%\Programs\HQAgent-Hub`，数据根目录固定 `%LOCALAPPDATA%\HQAgent-Hub`。
Agent 不写安装目录。首次运行创建数据子目录，以独占内核句柄持有单实例锁。
监听 `127.0.0.1` 随机高位端口后，原子写 `runtime/update-agent.json`；Token 为 32 随机字节，每次启动轮换。
描述符及受控更新目录去继承、只留当前用户；HTTP 拒绝所有 Origin、错误 Host、非 loopback 和错误 Bearer。
生产错误响应不回显内部 Token、Hub Token、上游响应正文或网络错误详情。

将 `config/update-trust.example.json` 的内容保存为数据目录下的 `config/update-trust.json`，填写实际 OTA 地址和代码签名证书指纹。
示例是本轮生成的独立测试公钥；私钥位于仓库外，不随配置交付。
缺少可信密钥/证书时不允许完成验签；没有忽略签名的开关。

已提供冻结路由的 state、check、download、cancel、install、result、releases。
download 在进程生命周期内后台运行；check 当前同步执行，W1 默认 5 秒代理超时需要联调调整。
安装只消费 W1 已完成的 `/internal/drain/state` 与 `/internal/backup/database`，不重做排空或 SQLite 备份。
缺少 Desktop/Core/本 Agent/任一已登记 Worker 时拒绝 Plan；不会自动杀掉未排空的旧进程。
生成 Plan 后复制并启动独立 Updater，再退出自身。

**尚未完成的协议能力**：冻结 OpenAPI 未定义 events 的媒体类型/包络、defer 路径和 acknowledge 路径。
events 明确返回 501 `FEATURE_UNAVAILABLE`；不另造事件协议或 Hub seq。
没有结果时使用 204（须由 W0 补充该响应）；有结果时返回裸生成 `UpdateResultView`。
W1 对 `success` 字段的包络判断需修复，否则不能正确读取裸失败回执。

详细限制和实测输出见 `.hqagent/handoffs/T-W6-updatekit.md`。
