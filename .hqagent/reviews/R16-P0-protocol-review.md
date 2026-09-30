# R1.6-P0 附件协议审核记录

- 工作包：R1.6-P0（对话附件协议，0.10.0 / wireRevision 4 / D52）
- 实施：codex 会话 01a0ceda（gpt-6-astra，high），分支 feat/remote-protocol，回执 `.hqagent/handoffs/R16-P0-protocol.md`
- 合入：integration/phase1（本地合入，2026-09-30；等 P1 服务端完成后一起推送，避免 CI 中途变红）

## 1. 主代理裁决

| 编号 | 问题 | 裁决 | 依据 |
| --- | --- | --- | --- |
| 偏差 | 方案 §8 写 wireRevision 3 | 改为 4，服务端支持 [1,2,3,4] | 3 已被 R3 原生会话占用 |
| Q1 | 暂停远程时 Worker 能否上传电脑本机消息的附件 | 能。暂停只禁浏览器上传与手机发送，两端下载不受影响 | D50「暂停不影响电脑同步」直接适用 |
| 图片能力 | Claude CLI 图片输入方式未经验证 | 分入口 / 实现 / 实测三层，P2 实测前取保守值，发送前拒绝 | 不凭 CLI 帮助宣称支持 |

## 2. 独立复核（主代理本机重跑）

```text
pwsh -NoProfile -File scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：507 个类型，373 个 Contract Fixture
python -X utf8 -B packages/protocol/remote/api-contract.py
API contract verified: 39 current + 8 planned HTTP operations; 92 error codes; self-contained bundle; examples/auth/request IDs consistent
python -X utf8 -B -m pytest packages/protocol/tests scripts/protocol/tests -q -p no:cacheprovider
608 passed in 46.27s
```

提交信息无署名。

## 3. 审核结论：通过

契约覆盖了流式上传（raw octet-stream、64KiB 分块、绕开 JSON 整包）、内容寻址 + 引用计数 + 逻辑配额、状态机（uploaded/reserved/attached）、grant 后启动前下载并校验、300s 总时限与强杀兜底、缩略图隔离子进程、删除栅栏与直接查存储的真删除验收、暂停矩阵、日志不记内容。

后续项（不阻塞）：本机缩略图只由服务器生成，未配对的电脑端只显示图标。以后可改为 Hub 本机生成，只改实现，不改协议。

## 4. 合入 integration 后的基线

- Hub 全量：490 passed / 5 failed / 9 skipped。5 项均为 integration 本地 venv 缺 segno（环境问题，CI 已装），补装后 `tests/test_runtime_cli.py` 6 passed。
- Server 全量：228 passed / 3 failed（`test_http_binding_completeness`、openapi 打包副本、错误码映射），为新协议尚无服务端实现的预期红灯，交 P1 修绿。

## 5. P1 回来后的附加核对项

用户要求为 OSS 预留接入方式，见《对话附件方案》§7.1 六条。P1 派出时尚未包含这一要求，回执回来后逐条核对，不满足的写进返修单。

## 变更记录

- 2026-09-30：Q1 裁决；0.10.0 审核通过，本地合入 integration；R1.6-P1 服务端派给 01a0ddec（high），预装 Pillow 12.3.0。

## 6. P1 服务端首次审核（2026-09-30）

- 交付 f9cfbe6 / a8c5b82 / 6c0b52c：8 个附件操作、wireRevision 4、内容寻址存储、配额、缩略图隔离子进程（POSIX rlimit / Windows Job Object）、删除联动；server 264 passed，smoke 通过，20MB 真实网络上传下载 RSS 增量约 0.91MiB。
- 返修 1（medium，01a0ddec）：①OSS 预留 §7.1 六条（业务代码仍直接用 store.temp / cas / path / stage.path，后端写死，删除意图 DB 与文件系统双份）；②maintain 每 5 秒全量扫附件与 CAS，改为到期清理 60 秒、孤儿扫描启动加每小时；③附件相关模块分号连写，按现有模块风格重排；④nginx 示例 proxy_pass 端口改为与站点一致（serverD 为 18090）。
