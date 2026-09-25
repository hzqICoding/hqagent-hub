# 连续任务对话交互验收

2026-09-25。按用户最终更正：主新建任务入口位于聊天右上角详情左侧。输入框去New/Continue，已有任务自动继续；首条新任务new。显式重置置于更多菜单，需确认、仅下一条生效、失败保留、允许撤销，不跨对话传递。运行/暂停/排队时不可重置。原会话恢复失败仍明确提示，不自动新建。

Store源3841a5e，集成571710c；UI源3170cfc，集成1937277。

实际验证：
```text
Store定向：19 passed
UI集成定向：38 passed
前端全量：40 files, 176 passed
vue-tsc --noEmit：通过
vite production build：通过
```

采用只更新静态资源、最后原子替换index.html的部署方式，未重启Worker。正式HTTP读取与构建逐字节匹配：
```json
{
  "indexMatchesBuild": true,
  "chatChunkMatchesBuild": true,
  "workerPidUnchanged": true,
  "chatChunk": "ChatPage-DKo3Hph1.js",
  "indexSha256": "b6dd1f5fa440614ac43fcf037a4c86cf29d3f25be358b6c1928a54b32ffd5eac"
}
```

CUA返回空浏览器列表，未做真实浏览器截图验收；DOM交互与按钮位置由组件测试覆盖。用户刷新后可检查实际视觉布局。
