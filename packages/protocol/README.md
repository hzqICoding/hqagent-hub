# @hqagent/protocol

HQAgent-Hub 的协议边界事实源。三端（Vue / Python / Go）的 DTO 都从这里生成，**不允许任何一端手写第二份**。

## 目录

```
VERSION                协议版本（不是产品版本，产品版本归 W7 管）
registry/              角色、能力、错误码的注册表，人类可读可编辑
schema/                JSON Schema draft 2020-12（子集，见下）
openapi/
  local-hub.v1.yaml            Vue/Tauri 唯一的网络契约
  update-agent.internal.v1.yaml Local Hub ↔ Update Agent 私有 API
events/event-dictionary.md     事件语义与状态迁移的唯一事实源
fixtures/contracts/    原子 Golden Fixture（单类型样本，不是 UI 场景）
generated/{ts,python,go}       生成物，禁止手改
```

## 用法

```powershell
pwsh scripts/protocol/generate.ps1                  # 重新生成三端 DTO
pwsh scripts/protocol/validate.ps1                  # 结构 + 注册表 + Fixture 校验
pwsh scripts/protocol/validate.ps1 -CheckGenerated  # 额外检查生成物是否漂移（CI）
```

导入方式：

```ts
import type { TaskDetailView, HubEvent } from '@hqagent/protocol'
```
```python
from protocol.generated.python import TaskDetailView, HubEvent
```
```go
import "hqagent.local/protocol"   // 通过 replace 指向 packages/protocol/generated/go
```

## 为什么是自建生成器

分工方案 §5.1 要求"固定工具及版本"。这里没有用 `datamodel-code-generator` + `json-schema-to-typescript` + `quicktype` 三件套，而是用仓库自带的 `scripts/protocol/generate.py`（零第三方依赖，只用 PyYAML 读注册表）。

原因是 CI 有一条门禁：`generate + git diff --exit-code`。外部生成器的版本漂移会让同一份 Schema 在不同机器上产出不同文本，把这条门禁变成噪音。自建生成器随仓库版本化，产出完全确定。

代价是只支持本仓库实际用到的 Schema 子集：

- `type: object` + `properties` + `required` + `additionalProperties: false`
- `string` / `integer` / `number` / `boolean`，可带 `enum` / `format` / `pattern` / `const`
- `array` + `items`
- `$ref: "<file>.json#/$defs/<Name>"`
- 自定义关键字：`x-registry`（值域来自注册表）、`x-generic-params` / `x-generic`（泛型容器）、`x-extends`（继承）、`x-map-value`（Record）、`x-go`（同时生成 Go）

支持 `oneOf` 的 TS 联合与 Python `RootModel`、显式 `null`。新远程对象可用 `x-wire-strict` 启用边界约束；旧DTO保持原语义。Go的 `x-go` 闭包不启用联合。

**不支持** `anyOf` / `allOf` / 条件校验；跨消息关系由契约语义和消费方验证。不要绕过生成器手写DTO。

## 命名约定

- 线上字段名一律 **camelCase**；枚举值一律 **snake_case 字符串**（`not_logged_in`、`draining_tasks`）。
- Python 侧属性是 snake_case，通过 pydantic `alias` 映射到线上的 camelCase，`populate_by_name=True` 两边都能用。
- `from`、`in` 这类 Python 关键字字段，属性名加尾下划线（`from_`），线上名不变。

## 已验证

FZ-1 冻结时三端均实测通过，不是"应该能用"：

| 端 | 命令 | 结果 |
| --- | --- | --- |
| TypeScript | `tsc --noEmit`（strict） | 0 |
| Python | pydantic v2 对 7 个 Fixture `model_validate` + 按别名 round-trip | 7/7 |
| Go | `go build ./...` + `go vet ./...` | 0 / 0 |


## Hub Server 对外规范（0.8.0）

当前对外调用入口见 [api-guide.md](remote/api-guide.md)，覆盖全部HTTP操作、PAT/设备管理、错误总表、requestId排查和Worker WSS索引。OpenAPI事实源为 [remote-hub.v2.yaml](openapi/remote-hub.v2.yaml)，公开JSON发布物为 [remote-hub.v2.bundle.json](openapi/remote-hub.v2.bundle.json)。业务实现与公开端点由P1适配，不能把文档冻结当作部署完成。

使用仓库虚拟环境运行：

```powershell
python packages/protocol/remote/api-contract.py --write  # 更新bundle、接口索引和错误表
python packages/protocol/remote/api-contract.py          # 检查路由/示例/鉴权/错误表/生成文档漂移
pwsh scripts/protocol/validate.ps1 -CheckGenerated       # 既有DTO/Fixture/三端生成物校验
python -m pytest packages/protocol/tests/test_devices_api.py -q -p no:cacheprovider
```

HTTP包版本0.8.0与Worker线路修订1/2分离。新HTTP码不进入旧Worker错误值域；详细兼容与交接见 [R1.5-contract.md](remote/R1.5-contract.md) §9。

### R1历史基线

结构：`schema/remote.json`；HTTP：`openapi/remote-hub.v2.yaml`；连接帧、owner隔离、控制结果与事务规则：[R1-contract.md](remote/R1-contract.md)。D40/D41沿用现有执行内核，不引入Attempt或新TaskStatus，不改变本地接口。
