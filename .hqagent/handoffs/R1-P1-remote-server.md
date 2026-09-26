---
wp: R1-P1
status: needs-decision
scope_declared: [apps/server/**, .hqagent/handoffs/R1-P1-remote-server.md]
scope_touched: [.hqagent/handoffs/R1-P1-remote-server.md]
build: fail
tests: fail
commit: dcf7ee699a3914561ee6715ba41db7d5bf229d46
open_questions: 1
---

# R1-P1 开工前契约冲突回执

本轮未实现服务端。任务明确要求“遇到契约与需求矛盾，停下写 needs-decision，不要按猜测实现”，因此在确认下面的冲突后停止实现，只提交本回执。`build: fail`、`tests: fail` 表示交付验收尚未通过，不表示构建或 pytest 已运行并报错；没有应用代码、构建结果或测试通过数可报告。

头部 commit 指首次记录冲突及复现证据的提交；本次补录提交号不代表新增服务端实现。该提交后 `git log -1 --format=%B` 实际输出为 `docs(remote): record pairing response acceptance conflict`，已自查无署名；`git diff --check` 通过，工作区干净。

## 工作区与已确认约束

- 工作目录：`E:/OtherPro/HQAgent-Hub-worktrees/remote-server`。
- 分支：`feat/remote-server`，起始 HEAD：`872a90932b8896002a4901d33ea66487b2927d32`。
- 开始时 `git status --short` 无输出。
- 已核对 AGENTS.md、R1-contract.md、remote.json、remote-hub.v2.yaml、远程错误码、P0 设计取舍及 P1 注意事项、D40/D41、手机远程接入方案 §2/§3/§5/§6、技术方案 §3/§5/§9，并补读分工方案路径所有权与冻结规则。
- 0.6.0 是本轮实现基线；D42 不提前自行变更协议。
- 服务端只认证、配对、转发和暂存；不执行模型、不管理模型凭据或订阅。
- 没有修改协议、既有应用、docs 或共享根文件；没有安装依赖、连接服务器或执行部署。

## open_questions

### Q1：配对挑战响应必须含短码，与验收禁止任何响应体包含短码冲突

任务完成标准要求：

> 口令、Cookie、Authorization、设备 secret、配对码不出现在任何响应体与捕获的日志里

冻结契约与方案同时规定：

1. `packages/protocol/schema/remote.json` 的 `RemotePairingChallenge.required` 包含 `pairCode`，字段格式为 8 位短码。
2. `packages/protocol/openapi/remote-hub.v2.yaml` 的 `POST /api/v2/worker/pairing-requests`，201 响应 `x-dataSchema` 为 `RemotePairingChallenge`。
3. `packages/protocol/remote/R1-contract.md` §2 要求“认证响应、配对码响应 Cache-Control:no-store”；§3 定义 Worker 发起挑战、浏览器输入短码预览与确认的流程。
4. `docs/vnext/手机远程接入方案.md` §5.1 明确“Worker 生成设备凭据 → 服务端返回短期配对码 → 用户在已登录的手机上确认”。

因此，返回短码会违反本轮验收原文；删除短码则无法通过生成 DTO 校验，并破坏冻结的配对流程。没有通过响应头、WS、自加字段或修改 DTO 绕过这一冲突。

**建议裁决（尚未执行）**：保留协议 0.6.0，明确 `RemotePairingChallenge.pairCode` 是响应体脱敏检查的唯一短码例外，仅向发起挑战的 Worker 返回（包括契约要求的合法幂等重放）；该响应 `Cache-Control: no-store`。短码仍不得进入日志、错误回显、URL、WS 帧、浏览器预览/确认响应及其它业务响应。口令、Cookie、Authorization 和设备 secret 仍不得进入任何响应体或日志。

如果产品确实要求短码不得出现在任何响应体，应由 P0 重新设计配对码交付方式并冻结 Schema/OpenAPI/Fixture；P1 不能自行变更。

## 实测证据

在上述 worktree 执行以下 PowerShell 命令，直接使用已安装的生成 DTO；没有另写验证模型，也没有打印真实凭据：

```powershell
@'
from protocol.generated.python import RemotePairingChallenge
from pydantic import ValidationError
payload = dict(pairRequestId='challenge-test',workerId='worker-test',expiresAt='2026-09-26T12:05:00Z',status='pending')
try:
 RemotePairingChallenge.model_validate(payload)
except ValidationError as exc:
 print('without pairCode:', [(e['loc'],e['type']) for e in exc.errors(include_input=False,include_url=False)])
else:
 raise AssertionError('missing pairCode unexpectedly accepted')
payload['pairCode']='ABCDEFGH'
validated=RemotePairingChallenge.model_validate(payload).model_dump(mode='json',by_alias=True,exclude_none=True)
print('with pairCode: DTO validation passed')
print('response necessarily contains pairCode:', 'pairCode' in validated)
'@ | .venv/Scripts/python.exe -X utf8 -
```

真实输出（退出码 0）：

```text
without pairCode: [(('pairCode',), 'missing')]
with pairCode: DTO validation passed
response necessarily contains pairCode: True
```

## 实现、验证与联调状态

- 模块划分与表结构：未创建；没有实际数据库、迁移或仓储实现。
- 契约规则落地：§2–§10 均尚未实现，不能把文档阅读视为规则已落地。
- `apps/server` pytest、协议 `pwsh scripts/protocol/validate.ps1 -CheckGenerated`、uvicorn/CLI/配对/假 Worker 冒烟：均未运行；本回执只提供上述冲突的 DTO 复现证据。
- pytest 临时目录：已知环境要求是将 TEMP、TMP、`--basetemp` 指向 worktree 内被 git 忽略的目录；本轮未执行 pytest，未实测触发 WinError 5。
- Dockerfile、Caddyfile、README、Backup API、可选 H5 挂载：尚未产出。
- P2/P3：当前没有可启动服务或测试账号 CLI，暂不能联调；裁决后继续原 R1-P1 范围，补齐实现、所有验收和真实输出。
- 后续帧版本识别与校验须集中一个模块，为 D42 的 `wireRevision` 调整保留边界；当前未声称已实现这一模块。
- 不请求额外依赖，也不新增根文件接线需求；当前唯一 open question 为 Q1。
