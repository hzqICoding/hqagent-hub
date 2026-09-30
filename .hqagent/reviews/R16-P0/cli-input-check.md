# CLI图片输入只读核对（2026-09-30）

只运行help/version，未传prompt、未创建或恢复会话、未调用模型。未读取登录配置、令牌、真实会话或附件。

实际版本输出：

```text
2.1.285 (Claude Code)
codex-cli 0.159.2
```

实际help相关输出：

```text
codex exec --help
  -i, --image <FILE>...  Optional image(s) to attach to the initial prompt
codex exec resume --help
  -i, --image <FILE>     Optional image(s) to attach to the prompt sent after resuming
claude --help
  --input-format <format>  Input format (only works with --print): text or stream-json
```

精确字段/空白以CLI help为准，此处仅摘取相关内容。Codex是exec输入入口证据，不证明Hub当前App Server路径已经验证。Claude仅证明stream-json入口，不能证明图片编码已接线；apps/hub/adapters/claude_adapter.py的_launch当前输出stream-json但输入仍是普通message字符串。P2须验证当前实际传输/Runtime/模型组合后才上报supported；本次catalog合成默认样例为unknown，未把帮助命令当真实图片识别验收。正向supported Fixture只是合成契约样本。

Q1暂停边界已经由主代理裁决，记录在D52/R1.6契约；此处不产生新的裁决请求。
