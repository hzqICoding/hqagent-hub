# Claude 网络配置继承修复

## 范围与行为

- 独立工作区`claude-network`，基线`eab2c5b`。仅修改Claude适配启动/进程环境、测试及本回执，未触碰前端未提交改动。
- `command_environment('claude')`只剥离`CLAUDECODE`、`CLAUDE_PID`两个嵌套标记，不再删除全部`CLAUDE_CODE_*`。Worker既有的代理、云供应商、证书和认证环境变量均保留。
- 每次启动读取`CLAUDE_CONFIG_DIR/settings.json`，未指定时读取`~/.claude/settings.json`。仅从`env`补齐白名单内的代理、网络认证、供应商路由与证书配置；显式Worker环境优先，包括空值。配置不可读或格式错误时报错，不静默丢弃代理配置。
- `detect`、`health`与执行进程使用相同环境构造方法。配置值只进入子进程环境，不放入命令参数、HTTP响应或日志，不改写用户配置。
- 保留`--safe-mode`及只读工具限制。不会执行PowerShell包装函数，也不会因为继承代理而启用用户钩子、插件或任意`NODE_OPTIONS`。仅保存在Shell函数里的临时配置仍需通过Worker环境提供；本机代理已保存在用户settings中，本轮实测值一致。

## 自动化验证

cwd：`E:/OtherPro/HQAgent-Hub-worktrees/claude-network/apps/hub`

```text
E:/OtherPro/HQAgent-Hub-worktrees/vnext-integration/.venv/Scripts/python.exe -B -m pytest tests/test_claude_environment.py tests/test_process_io.py adapters/tests -q -p no:cacheprovider
30 passed, 1 warning in 0.51s
```

新增8项覆盖：只删除嵌套标记、代理/认证/云供应商参数保留、UTF-8 BOM用户配置、自定义配置目录、大小写与空值优先级、拒绝任意配置代码、配置损坏不回退直连、探测与执行环境一致、Codex环境不受影响。Warning为既有依赖弃用提示。

## 本机真实验证

首次只检查内存中的配置匹配及代理TCP可达性，不输出地址、账号或密钥：

```text
saved_proxy_values_match_child {"HTTP_PROXY": true, "HTTPS_PROXY": true, "ALL_PROXY": true, "NO_PROXY": true}
proxy_configured True scheme_supported True
configured_proxy_tcp_reachable True
user_settings_unchanged True
```

随后以修复后的`command_environment('claude')`和现有原生CLI，在独立临时目录启动一次`--safe-mode --print --output-format stream-json --verbose --permission-mode dontAsk --permission-prompts none --tools "" --max-turns 1 --session-id <新UUID>`。提示仅要求回复`HQ_NETWORK_OK`，未访问用户项目或调用工具。通过Windows `GetExtendedTcpTable`按该原生CLI的PID核对远端地址/端口等于配置中的代理，实际输出如下：

```json
{"native_claude_connected_to_configured_proxy": true, "process_exit": 0, "result_subtype": "success", "reply_marker_received": true, "user_settings_unchanged": true}
```

这证明本机当前Claude确实通过已配置代理完成一次真实模型请求，不只是版本/登录态检查。请求消耗少量供应商额度，未保存或打印模型私有内容与认证信息。
