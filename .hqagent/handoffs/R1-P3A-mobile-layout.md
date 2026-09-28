# 手机移动端纯布局适配交付 (R1-P3A)

- 分支：`feat/remote-web-mobile`
- Worktree：`E:\OtherPro\HQAgent-Hub-worktrees\remote-web`
- 基线：`integration/phase1@6f38217`（41 files / 201 passed）
- 协议依赖：本轮为纯展示层/布局层适配，不修改 store 数据流与协议契约
- 变更范围：`apps/desktop/index.html`、`apps/desktop/src/**`、`.hqagent/handoffs/R1-P3A-mobile-layout.md`

## 交付说明

### 1. `/chat` 手机移动端工作台适配 (视口 ≤ 430px)
- **左侧「项目任务」侧边栏抽屉化 (`ChatSidebar.vue` + `ChatPage.vue`)**:
  - 在大屏 (≥ 768px) 保持固定列排版 (`static md:translate-x-0`)。
  - 在移动端 (≤ 430px 及窄屏) 转换为全屏遮罩抽屉 (`fixed inset-y-0 left-0 z-50` + `backdrop`)，左上角通过汉堡按钮一键滑出。
  - 选中任意对话后，侧边栏自动收起 (`@select="isMobileSidebarOpen = false"` 与 `activeConversationId` 联动关闭)。
  - 抽屉右上角提供符合触控标准的关闭按钮 (`X`, ≥ 44×44px)。
- **右侧「执行详情」抽屉适配 (`RunSnapshotDrawer.vue`)**:
  - 移动端下作为遮罩抽屉弹出 (`fixed inset-y-0 right-0 z-50 w-full sm:w-[380px]`)，避免挤占中央聊天主屏。
  - 抽屉顶部提供标准触控关闭按钮 (`X`, ≥ 44×44px)。
  - 越界修改、变更文件、步骤代码与参数预览均配置 `overflow-x-auto break-all max-w-full`，彻底杜绝撑破页面宽度的横向滚动。

### 2. 触控目标与窄屏操作友好性
- 移动端触控目标均达到 ≥ 44×44px 标准：
  - `/chat` 顶部左侧任务列表抽屉按钮 (`min-w-[44px] min-h-[44px]`)。
  - `/chat` 顶部右侧「新建任务」按钮 (`min-w-[44px] min-h-[44px]`)。
  - `/chat` 顶部右侧「更多任务操作」按钮 (`min-w-[44px] min-h-[44px]`)。
  - `/chat` 顶部右侧「执行详情」按钮 (`min-w-[44px] min-h-[44px]`)。
  - 抽屉内各任务项高度达 `min-h-[44px]`，右侧菜单触发按钮 `min-w-[44px] min-h-[44px]`。
  - 消息复制快捷按钮提升为移动端触控友好尺寸。

### 3. 虚拟键盘与输入区域适配 (`ChatComposer.vue` + `index.html`)
- `index.html` viewport meta 增加 `viewport-fit=cover, interactive-widget=resizes-content`，适配 iOS Safari 与 Android Chrome 软键盘弹起时的视口重绘。
- 输入栏底部增加安全区域适配 `pb-[max(0.75rem,env(safe-area-inset-bottom,0px))]`。
- 发送与停止按钮保持 ≥ 44×44px 点击区域，状态提示文字在窄屏上自适应折叠为图标+紧凑标签。

### 4. 全局应用骨架与导航适配 (`AppLayout.vue` + `AppHeader.vue` + `AppSidebar.vue` + `AppStatusBar.vue`)
- 全局主侧边栏 `AppSidebar.vue` 在移动端改为可收起抽屉，通过全局顶部栏左侧汉堡按钮唤起，点击菜单项自动导航并收回抽屉。
- 全局状态栏 `AppStatusBar.vue` 在窄屏下隐藏次要状态文本，保持关键 Hub 状态、日志抽屉与检视器触发入口，禁止页面级横向溢出。

### 5. `/scenes` 场景与角色页面响应式 (`ScenesPage.vue`)
- 在移动端自动切换为**单列流式布局** (`flex-col md:flex-row`)。
- 顶部「场景清单」采用水平卡片轻量滑动，支持快速切换当前配置场景。
- 下方场景详情与角色列表纵向平铺，角色阶段调整（上移、下移、移除、启用开关、指令配置、执行 Agent 与模型选择）完全可用。
- 各操作按钮均适配移动端触控尺寸。

### 6. 非回归保证
- IME 中文输入法合成状态按 Enter 不误发消息 (`if (e.isComposing) return`)。
- 每任务草稿按 `conversationId` 隔离与还原逻辑保持完好。
- 会话切换不串流。
- 任务上下文重置保持在「更多任务操作」菜单中，且处于执行期时正常置灰。

## 验收结果

```text
pnpm --filter @hqagent/desktop test
结果：42 files passed (42), 207 tests passed (207)
新增测试：src/pages/chat/ChatMobile.test.ts (6 tests passed)

pnpm --filter @hqagent/desktop typecheck
结果：vue-tsc --noEmit 检查通过，0 错误

pnpm --filter @hqagent/desktop lint
结果：eslint src 检查通过，0 错误

pnpm --filter @hqagent/desktop build
结果：生产构建通过
```
