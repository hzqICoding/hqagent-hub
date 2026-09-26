# 项目多任务工作台验收（2026-09-26）

## 协议与后端

协议0.4.0：160个类型，12个Contract Fixture。362d3ba定义metadata与归档，1b28679补Fixtures。后端源f781fe6，集成496420d。

```text
pwsh scripts/protocol/validate.ps1 -CheckGenerated
协议校验通过：160 个类型，12 个 Contract Fixture
python -B -m pytest -q -p no:cacheprovider
190 passed, 4 warnings in 25.25s
```

升级前排空activeTasksRemaining=0、step=ready、backupCompleted=true。本轮metadata存于原payload_json，无数据库schema迁移。服务监听仍127.0.0.1:8765，数据目录仍E:/tmp/hqagent-n0-trial。

## 真实HTTP验收

运行 `.venv/Scripts/python.exe -B E:/tmp/hqagent-project-workbench-acceptance.py`，仅在已登记临时工作区创建无模型执行的验收对话。操作包括创建、重命名、同键重放、旧版本冲突、归档、归档拒发、恢复及再次归档。结果：

```json
{
  "conversationId": "conversation_96dd8d3af2a34d55a7f15c555a5fa29e",
  "workspaceId": "ws_19bbce7b11a5",
  "renameTrimmed": "重命名后归档的验收任务",
  "sameKeySameRevision": true,
  "staleVersionHttpStatus": 409,
  "staleVersionCode": "CONFLICT",
  "archivedMessageHttpStatus": 409,
  "archivedMessageError": "CONFLICT",
  "archiveRestoreWorks": true,
  "noModelSessionsCreatedOrChanged": true,
  "historicalMessagesUnchanged": true,
  "runsCreated": 0,
  "finalRevision": 5
}
```

无新Run或模型Session；归档验收记录保留在已归档列表。版本只跟踪metadata，不因消息与Run刷新递增。

## 旧记录保留

升级前后逐记录摘要核对：

```json
{
  "local_conversations": {
    "oldCount": 10,
    "allOldRecordsUnchanged": true
  },
  "local_messages": {
    "oldCount": 52,
    "allOldRecordsUnchanged": true
  },
  "local_scenes": {
    "oldCount": 3,
    "allOldRecordsUnchanged": true
  },
  "sessions": {
    "oldCount": 20,
    "allOldRecordsUnchanged": true
  }
}
```

## 前端

前端源3c49829→集成0da7eb8；页面测试清理补丁0df440b→5072c07；主代理补任务控制迟到回包隔离da61373→47e0a75。

```text
前端定向：10 files, 65 passed
主代理控制回包隔离：2 passed
整合全量：41 files, 190 passed (6.93s)
vue-tsc --noEmit：通过
vite production build：通过 (5.99s)
```

首轮全量187通过、1项ChatPage重置菜单测试失败：测试未卸载mount和轮询，固定50ms等待在全量负载下不可靠。已改明确初始化等待并清理组件/Teleport，之后整合全量190通过。没有通过关闭产品校验来让测试通过。

关键交互回归：项目/归档分组、指定空项目新建、metadata版本冲突、A/B草稿及队列隔离、late SESSION_NOT_RESUMABLE切回仍可见、草稿revision不覆盖主动清空、PATCH迟到v2不覆盖已收到的v3、取消/重试回执不串到另一对话。

CUA实际返回apps=[]、browsers=[]，不能进行真实浏览器截图验收，不以DOM测试冒充视觉验收。


## 用户可复现的页面检查

1. 重新连接本地页面，确认左侧项目下分别列出对应任务；折叠再展开不新建模型会话。
2. 点目标项目的加号，检查新建弹窗默认项目；点右上新建任务，应默认当前任务所属项目。
3. 在任务A输入未发送文字，切B输入另一段，再切回A检查草稿。无需发送给模型即可验证。
4. 对已结束任务重命名后刷新；归档后从“已归档”查看并恢复。运行中任务应禁用归档。
5. 检查右侧详情中的重试/继续在归档时被禁用，先恢复才能操作。

草稿只保证当前页面会话内切换保留，不承诺刷新、退出或跨设备保存。重命名/归档是后端持久化，刷新后仍保留。


## 页面发布

构建输出E:/tmp/hqagent-project-ui-20260926，静态资源复制到现有web root，最后原子替换index.html。旧hash资产保留，以免已打开页面懒加载失败。真实HTTP字节核对：

```json
{
  "indexMatchesBuild": true,
  "chatChunkMatchesBuild": true,
  "workerNotRestartedForStaticUpdate": true,
  "chatChunk": "ChatPage-CaBvLcIU.js",
  "indexSha256": "0da92a08a0ce9846fc5f3b2157003ade397eb7ecc1305fe36bad4df77ec41c22"
}
```

后端升级时已重启一次并备份；此静态更新未再重启。用户重新连接/刷新后可做上述页面检查。
