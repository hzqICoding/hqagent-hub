# 自定义场景与角色模板验收（2026-09-26）

## 交付

协议0.5.0，165类型、14 Contract Fixtures。新增场景创建、角色模板创建/编辑/列表及可选来源显示字段；无新的权限类型。角色模板基础类型为analyst/planner/developer/reviewer，每场景最多四个顺序阶段，各基础类型最多一次。运行角色ID仍使用基础类型，权限仍由现有Catalog与Worker约束。

后端源a3b6168→集成4e1157f；前端2956cdd→bfc39f8、260c7f6→55012b0；通用参数校验错误修复620c98b→3e0d99e。两已有子代理复用，独立worktree，主代理整合部署。

## 实际验证输出

```text
协议：165 types / 14 Contract Fixtures
后端完整：199 passed, 4 warnings in 24.57s
前端完整：41 files / 201 passed in 6.01s
vue-tsc --noEmit：通过
vite production build：通过 (5.27s)
```

发现并修复旧FastAPI异常处理API不兼容：RequestValidationError.errors不支持Pydantic风格kwargs，导致null请求500；改为无参调用后只保留type/loc/msg，不回传input/ctx。3项定向校验通过，新模板/场景HTTP null回归通过。

## 真实场景与连续对话

仅临时项目，创建V1模板并应用场景，模板更新V2后，场景仍保存V1副本。真实Claude执行返回V1标记，同对话Continue仍使用原生session。

```json
{
  "templateId": "role_template_357b58323cda421db6842294633dfd99",
  "sceneId": "custom_scene_d4c2e47430494900b31b45b1f20d196e",
  "conversationId": "conversation_666b846d67c24292931aa532896f3591",
  "runId": "run_0551afc187324ea68a54914087089268",
  "templateRevisionAfterUpdate": 2,
  "sceneTemplateRevision": 1,
  "templateUpdateDidNotMutateScene": true,
  "staleTemplateVersionHttpStatus": 409,
  "duplicateRoleHttpStatus": 422,
  "readOnly": true,
  "runStatus": "succeeded",
  "taskId": "task_fff96b238195",
  "toolCalls": 2,
  "nodeSummaries": [
    "CUSTOM_TEMPLATE_V1_OK：模板配置已加载。本轮角色为 analyst，访问模式为只读。按照要求，本轮没有调用任何工具，没有读写文件，也没有运行命令，所以授权目录里的内容没有经过实际检查。"
  ],
  "sceneSnapshotTemplateRevision": 1,
  "markerFound": true,
  "passed": true,
  "toolEventNames": [
    "StructuredOutput",
    "tool_result"
  ],
  "resourceToolCalls": 0,
  "gitStatus": "",
  "verificationNote": "Initial zero-tool-event assertion counted CLI StructuredOutput response protocol. Inspecting actual events confirms only StructuredOutput and its success receipt, no filesystem or command tools.",
  "continueRunId": "run_b19ac703b0b1407f81aae753707ef216",
  "continuation": {
    "status": "succeeded",
    "firstSessionIds": [
      "session_2f63a08b69e94802a3d7241d07a73d18"
    ],
    "continuedSessionIds": [
      "session_2f63a08b69e94802a3d7241d07a73d18"
    ],
    "sameHubSession": true,
    "nativeSessionIds": [
      "67d3b06a-62db-4cfd-9b9d-babb488828f6"
    ],
    "sceneTemplateRevision": 1,
    "nativeIdsFromStartedEvents": [
      [
        "67d3b06a-62db-4cfd-9b9d-babb488828f6"
      ],
      [
        "67d3b06a-62db-4cfd-9b9d-babb488828f6"
      ]
    ],
    "sameNativeSessionVerified": true,
    "toolEventNames": [
      "StructuredOutput",
      "tool_result"
    ]
  }
}
```

首次脚本把StructuredOutput的两条协议事件误计为资源工具，零事件断言失败；核对实际事件仅结构化结果提交及成功回执，无Read/Glob/Grep/命令操作，临时项目git status为空。未更改业务项目。修正的是验收分类，不是放宽目录或工具权限。

## 数据升级保留

升级前ready/activeTasksRemaining=0/backupCompleted=true；数据库4→5新增模板表，核对旧记录摘要：

```json
{
  "schemaVersionBefore": 4,
  "schemaVersionAfter": 5,
  "local_conversations": {
    "oldCount": 11,
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
  },
  "local_runs": {
    "oldCount": 26,
    "allOldRecordsUnchanged": true
  }
}
```

## 静态页面发布

{
  "indexMatchesBuild": true,
  "sceneChunkMatchesBuild": true,
  "workerNotRestartedForStaticUpdate": true,
  "sceneChunk": "ScenesPage-D2ggKHW0.js",
  "indexSha256": "38b03d8f84c6a3fd2f6bc780e90474a230f2e55e8d1909f4cca52f5f5972bd7c"
}

页面资源先复制，最后原子替换index；无第二次Worker重启。CUA无可用浏览器surface，未声称完成视觉截图验收。

## 使用与边界

进入“场景与角色”：新建空白/复制场景；角色模板管理中选择基础类型并填写名称职责；自定义场景可增减排序阶段、选择Agent模型和强度。保存后新建对话选择新场景。模板应用是副本，修改模板不自动更新已保存场景或Run快照。配置变更后的Continue保留既有严格校验。original_planner仍要求启用顺序恰planner→developer→reviewer，不支持其它阶段插入该模式。无删除模板/场景、任意并行或循环功能；不是通用DAG编辑器。
