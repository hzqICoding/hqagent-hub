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

## 7. integration CI（cc17608，run 36696935866）红灯与处理

- protocol：`test_devices_api.py:170` 写死 `runtime_count==39`（8 个附件操作未实现），服务端实现后为 47。排在 P2 之后交协议会话 01a0ceda（low）改为 47。
- server macOS：`test_image_thumbnail_and_capability_fail_closed`、`test_business_uses_only_blobstore_interface` 缩略图为 unavailable。推断 `thumbnail_child.py` 在 darwin 上 `setrlimit(RLIMIT_AS)` 不受支持，子进程 fail-closed 退出。部署目标 Linux 不受影响。排在 P2 之后交服务端会话 01a0ddec（medium）。
- hub 三平台 11 项 `assert 5 == 4`：`tests/test_r15_joint_server.py:117` 写死服务端 `PRAGMA user_version == 4`，P1 迁移后为 5。P2（正在跑，已合入 cc17608）应顺带修正，审核时核对。

## 8. P3 前端审核（2026-09-30）

- 01a0e638（high）与 P2 并行开发，交付 6ac9e12 / 49e4bc3：手机与电脑附件入口、限制值来自接口、增量 SHA-256（无新依赖，gzip 1.5KB）、raw 上传进度、图片能力发送前预检、缩略图只用服务端产物、下载 octet-stream、同步状态与本机可用分开显示；lint / typecheck / build 通过，vitest 61 文件 397 项通过。
- 截图核对手机亮 / 暗、电脑各附件状态正确。合入 integration。
- 后续项：手机暗色模式下顶栏设备名与按钮在截图中不可见，本包未改顶栏，属既有问题或截图环境所致，联调时真机确认。真实 Hub 附件链路待 P2 合入后联调。

## 9. P2 合入与 CI 全绿、真实联调首轮（2026-09-30）

- P2（01a0de45，high）交付 5f1129b / b4522ea / 836f71c：Hub 515 passed / 9 skipped，主代理 integration 复跑一致。smoke macOS RSS 小修（ce1a634）合入。CI run（34058ae）protocol / desktop / hub ×3 / server ×3 全绿。
- 真实联调（joint/hub-data16 全新配对，r16joint.py）：直接协商修订 4；catalog 图片能力 unknown；手机上传 markdown 201 → 发送 202 → Worker 下载校验 → 交给 Agent 链路通，但 Agent 未读取附件（角色提示词禁止读取根目录外文件，附件路径被 JSON 转义）。
- verify-image：Claude Code 2.1.285 五项全通过；codex-cli 0.159.2 new / error 通过，resume / mixed-five / cancel 失败（续接轮被提前终止、取消探测未启动第二会话、128px 探测图识别不稳）。另 Hub 日志有 GBK 解码后台线程异常。
- 返修 1（01a0de45，medium）已派：提示词附件授权与原样路径、Codex 续接回合结束判定、取消探测、探测图放大、GBK 解码。

## 10. 联调第二、三轮（2026-09-30 ~ 10-01）

- 返修 1 后：手机发 markdown，Agent（Codex）读出暗号与端口，附件读取修复确认；GBK 异常消失；Codex verify-image new / resume / cancel 通过，mixed-five 因 shell 读取附件被 PathGuard 判 PATH_NOT_ALLOWED。
- 同轮验收通过：图片上传生成缩略图（ready，attachment + nosniff）；未验证 Agent 发送前 422 AGENT_IMAGE_UNSUPPORTED；exe 改名 .txt 与 SVG 上传 415；限制值由接口下发。
- 返修 2（cd5cc32，精确附件只读 shell 放行）合入后：Codex verify-image 五项全通过；catalog native 两个 Agent 均 supported。
- 新发现：默认场景角色未绑定 Agent，能力解析与执行解析不一致，场景图片能力恒为 unknown。返修 3（01a0de45，medium）已派。
- 主代理脚本修正：r16joint.send_and_wait 改为只认发送后新出现的回复（首次复测曾误读上一轮旧回复）。

## 11. 用户真机反馈后的界面返修与二次部署（2026-10-03）

- 前端返修 1（8615a72 / fac5125）：暗色主题输入框对比度统一修复、手机顶栏可见；配对页内扫码（同源校验、jsqr 懒加载 47KB gzip、释放摄像头）。443 项通过。
- 前端返修 2（66ce28f）：共用确认弹窗与底部选择面板，退出二次确认；去掉重复状态文字，在线绿 / 离线橙；顶部「+」新话题，去掉单选，默认继续上下文；输入行等高对齐；占位提示减弱。462 项通过。主代理补设备列表离线标签为橙色。
- 服务端 set-password 命令（8c71c7b）：改密后删除该账号浏览器会话，PAT 保留。304 项通过。
- 电脑连接手机页默认服务器 https://hqremote.hylucky.top（0f5a8e0）。
- CI c23d375 三平台全绿；部署 serverD（仅服务端代码与 web，依赖未变），线上网页 bundle 与构建一致。

## 12. 用户真机反馈修复（2026-10-03）

- 新对话首条 continue 报 SESSION_NOT_RESUMABLE：Hub 返修 4（da553a1）无可续接上一轮时自动新建；前端返修 4（4200633）显示 Hub 具体原因。
- 原生会话 51/56 显示「CLI 版本尚未验证」：前端返修 3 按可用性分组；Hub 返修 5（61aee66，新会话 01a0ff62）结构普查（Codex 33.7 万、Claude 8.2 万条，只含版本 / 类型 / 计数，已核无路径与正文）后放宽为 Codex 0.98.0–0.159.2、Claude 2.1.251–2.1.288，同 major 未来版本结构校验通过才读取；用户电脑 56/56 可读。
- 本机浏览器会话持久化（7e45fd9）：摘要入库、30 天滑动续期、上限 20、`runtime.pair --revoke-sessions`。
- 返修 5 上线后用户 Hub 因 REMOTE_SYNC_CONFLICT 本地冻结（服务端未冻结）：根因为已导入原生对话的源版本 / 活动状态变化未递增 metadataVersion。修复（9a6e6ae）递增版本，并新增仅限「本机同步冲突冻结」的 `remote resync --confirm-reset` 恢复（服务端 ready 后 reset 再新代次补传）。主代理在用户电脑执行恢复：paired online，手机可见 14 个对话，无需重新配对。

## 13. 0.10.1 合入与观察项（2026-10-03）

- 协议 0.10.1（7f9c8d2）、前端（c5626c6 / 3d96096）、Hub（cb92d51 起，新会话 01a0ffac）合入；裁决 Hub Q1：未 ACK 审批事实时暂时阻塞本机删除，作为后续协议修订项。server bundle 刷新并修正测试版本常量。integration：server 304、Hub 702 passed。
- 用户电脑：旧验证记录 legacy_unbound（预期），但 detected_version 为 `2.1.288 (Claude Code)` / `codex-cli 0.159.2` 未提取 semver → 四个目标 target_unavailable，无法发起验证。返修派 01a0ffac（medium）。
- CI 4f8f142：hub windows `test_remote_dispatch.py::test_ws_queue_backpressure_does_not_disconnect_when_more_than_200_commands_arrive` TimeoutError（该 job 用时 7:47，明显偏慢，前几轮均通过），其余 7 项通过。观察：再次出现则派返修，改为按完成条件等待。

- 0.10.1 返修 1（5a49109，共用版本解析 adapters/versions.py）合入；CI 1e6c1e8 三平台全绿（Windows 背压超时未复现，判定偶发）；部署 serverD（openapi 0.10.1）。用户电脑经新作业接口完成四个目标验证（Claude 默认 / opus、Codex 默认 / gpt-6-astra），全部 succeeded + cleanup confirmed，线上 catalog 全部场景与原生 supported。
