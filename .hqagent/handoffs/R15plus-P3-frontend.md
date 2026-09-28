# R1.5+-P3 前端：设备管理、暂停 / 恢复、API 令牌管理（协议 0.8.0，D50）

协议 0.8.0 和服务端实现已经合入 integration，并同步到本分支。服务端的真实行为以 `apps/server` 为准，接口以 `packages/protocol/remote/api-guide.md` 为准。

## 必读

1. `.hqagent/handoffs/R15-P0-devices.md` 的「下游实施要点 · P3 前端」，逐条实现。
2. `packages/protocol/remote/api-guide.md`：第 2–8 节（约定、鉴权、设备、PAT、幂等、分页、requestId），以及第 10 节错误码总表。
3. `.hqagent/handoffs/R15plus-P1-server.md`：服务端的规则落点。

## 要做

范围：`apps/desktop/**`，类型全部从 `@hqagent/protocol` 导入。

### A. 手机端「我的电脑」改为设备管理

1. 每台设备同时显示两种状态：在线 / 离线、远程可用 / 已暂停。已暂停的用醒目标记，文案「远程操作已暂停」。
2. 设备操作放在「更多」菜单或设备详情里：
   - **暂停远程** / **恢复远程**：`PATCH /devices/{workerId}`，`remoteAccess` 取 `suspended` 或 `enabled`，带上当前的 `expectedVersion`。
   - **修改显示名**：修改 `displayName`，清空即恢复为电脑上报的名称。显示时优先用 `displayName`，其次 `deviceName`。
   - **删除设备**：`DELETE /devices/{workerId}`。二次确认文案要写清三点：
     - 这台电脑在服务器上的对话副本会被删除，电脑本地不受影响；
     - 电脑上正在执行的任务可能仍在继续；
     - 以后要再连接，只能在电脑端重新扫码。
   - 删除成功后，设备从列表中消失。
3. 「撤销设备」按钮**移除**。上一轮返修里「已撤销（N）」这个折叠分组保留，用来放 0.8.0 之前留下的撤销记录，每条给一个「删除」按钮。列表默认 `includeRevoked=false`，展开这个分组时才带 `includeRevoked=true` 拉取。
4. 如果 CAS 冲突（版本已变），自动重新读取设备，提示「设备状态已变化，请确认后重试」，重试时换一个新的 Idempotency-Key。
5. 删除返回 404 时，只有确认服务端支持 0.8（能力判断方式见 api-guide 与回执），才能当作「已不存在」处理。
6. 操作完成后重新读取设备状态，不能用本地乐观值覆盖。

### B. 暂停对对话页的影响

1. 当前电脑已暂停时，这些操作禁用，并提示「这台电脑的远程操作已暂停」，同时提供「恢复远程」入口：发送消息、新建任务、修改对话、批准审批、暂停 / 恢复 / 重试运行。
2. **取消运行、拒绝审批保持可用。**
3. 收到 `REMOTE_DEVICE_SUSPENDED` 时：保留输入框内容，刷新设备状态，并给出同样的提示。
4. 暂停不等于离线：历史照常可以浏览，同步照常。

### C. API 令牌管理页（手机端，新页面）

1. 入口放在「我的电脑」页的菜单或设置里，名称「API 令牌」。路由例如 `/remote/tokens`。
2. **列表**：显示名称、前缀、权限、创建时间、最后使用时间、到期时间、状态（有效 / 已过期 / 已吊销）；默认不显示已吊销的，可以切换显示。
3. **新建**：
   - 输入名称；
   - 三个权限各自一个勾选框，分别是 `devices:read`、`devices:manage`、`devices:delete`。**delete 不能因为勾了其他项被隐式带上**；勾选 delete 时额外提示「删除是破坏性操作」；
   - 有效期可选，默认 90 天，最长 365 天。
4. **秘密只显示一次**：
   - 签发成功后，弹窗显示完整令牌，提供复制按钮，提示「关闭后无法再次查看」；
   - 令牌只存在于这个弹窗组件的临时内存里，关闭弹窗即清空；
   - **不能写入 localStorage、sessionStorage、Pinia 持久化、日志、错误上报、URL**。
   - 同一个幂等键重放时，服务端只返回元数据，不返回秘密。这时显示「令牌已创建但无法再次显示，如未保存请吊销后重建」，并提供吊销入口。
5. **吊销**：二次确认后调用 `DELETE /api-tokens/{tokenId}`，成功后刷新列表。
6. 令牌管理只能用登录 Cookie 会话，网关不要加 Authorization 头。

### D. 错误与排查

1. 所有新错误码都加中文提示，写进 `remote-errors.ts`，与 api-guide 的错误码总表一致。至少包括：
   - `REMOTE_DEVICE_SUSPENDED`
   - `REMOTE_API_TOKEN_INVALID`
   - `REMOTE_API_TOKEN_EXPIRED`
   - `REMOTE_API_TOKEN_SCOPE_INSUFFICIENT`
   - `REMOTE_AUTH_AMBIGUOUS`
   - CAS 冲突
2. 请求失败时，错误提示里附上 requestId（取响应头 `X-Request-Id` 或信封里的 requestId），做成可以长按或点击复制的小字，方便排查。成功请求不显示。
3. 网关统一读取并保存最近一次失败的 requestId，只放在内存里。

## 测试

- A：
  - 两种状态的显示；
  - 暂停和恢复时带 version，冲突后刷新；
  - 删除需要二次确认，删除后从列表消失；
  - 旧的已撤销记录可以删除；
  - 撤销按钮已不存在；
  - displayName 优先显示。
- B：
  - 暂停时发送、新建、批准被禁用，取消和拒绝可用；
  - 收到 SUSPENDED 时保留输入。
- C：
  - scope 独立勾选；
  - 签发后秘密只在弹窗里出现；关闭后在 DOM、store、storage 里都找不到（断言 localStorage 和 sessionStorage 中没有 `hqr_pat_`）；
  - 重放响应显示为「无法再次显示」；
  - 吊销流程；
  - 请求没有带 Authorization。
- D：错误提示里带 requestId。

跑 lint、typecheck、`vitest run --minWorkers=1 --maxWorkers=2`、build，贴真实输出。如果能跑无头浏览器，补 375×812 的截图：设备管理菜单、暂停状态的对话页、令牌列表、签发弹窗（用示例令牌）。

回执写到 `.hqagent/handoffs/R15plus-P3-frontend-receipt.md`，列出所有被改动的旧断言。提交到 `feat/r15-web`。

commit message 不得出现任何 Claude / Anthropic / Codex / Gemini 署名，不写 Co-Authored-By，不写「Generated with」字样；每次提交后用 `git log -1 --format=%B` 自查。
