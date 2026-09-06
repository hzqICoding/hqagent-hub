# T-W6 第二轮审核结论

| 项 | 值 |
| --- | --- |
| 审核方 | W0 |
| 被审提交 | `3983b6a`（含合并提交 `2245f38`） |
| 审核日期 | 2026-09-06 |
| 结论 | **三项全部完成，证据经独立复现。这轮的诚实度是六个包里的标杆。** |

## 一、独立复现

| 项 | 自述 | W0 实测 | 一致 |
| --- | --- | --- | --- |
| 真合 main，协议 0.2.0 | 是 | `packages/protocol/VERSION` = `0.2.0`，不是临时导出目录 | ✅ |
| updatekit `go test` | ok 14.943s | `ok 15.147s` | ✅ |
| update-agent `go test` | ok 1.983s | `ok 2.150s` | ✅ |
| updater `go test` | 无测试文件 | 同 | ✅ |
| **updatekit `-race`** | ok 18.943s | **`ok 19.033s`** | ✅ |
| **update-agent `-race`** | ok 9.470s | **`ok 9.592s`** | ✅ |
| 无竞争报告 | 是 | 两轮均无 DATA RACE 输出 | ✅ |

### `-race` 这一条我一开始复现失败了，值得记一笔

我第一次跑 `CGO_ENABLED=1 go test -race`，拿到的是：

```text
cgo: C compiler "gcc" not found: exec: "gcc": executable file not found in %PATH%
```

和我派活时预判的一样（Windows 的 race detector 要 gcc/clang，不吃 MSVC）。
按常理这时候该怀疑自述造假。

但交接单 §4.2 **把这条失败原样记了下来**，然后写清了怎么解决的：从 LLVM-MinGW
官方 release 下载便携包到 `E:/tmp/hq-w6-toolchain`，附 URL、SHA256、
GitHub release asset digest、`clang --version` 输出，并明确
「**没有把 MSVC 当作 gcc 使用**」「未改系统 PATH、Go 全局配置、Visual Studio、证书库」。

我按它记的路径把工具链加进 PATH 重跑，两个模块都过，耗时对得上。
**它没有为了让这条变绿去改测试、跳过用例或动 `GORACE`**——交接单里还专门声明了这点。

派活时我写的是「装不上就如实报告装不上，不要为了让这条变绿去改测试或跳过」。
它既没有放弃，也没有作弊，而是找了条干净的路并把过程完整留痕。这是正确答案。

## 二、Job Object 收敛：实现是对的

`packages/updatekit/installer_job_windows.go` 抽读：

**`runInstallerProcess`（:112-161）**——`CREATE_SUSPENDED` 创建 → 
`AssignProcessToJobObject` → `ResumeThread`。顺序很关键：先挂起再入 Job，
堵死了「安装器刚启动就 fork 出子进程、而此时还没被纳管」这个竞态窗口。
Job 的 limits 里 `BREAKAWAY_OK` / `SILENT_BREAKAWAY_OK` **都没设**，后代逃不出去。

入 Job 失败时它终止那个**从未运行过的**进程而不是留个挂起态僵尸（:151-156），
这个边界也想到了。

**`waitInstallerJob`（:163-199）**——注释写得很准：
「Top-level exit alone never proves completion.」循环条件是
`exited && active == 0`，两个都满足才返回退出码；ctx 超时则返回
`ErrInstallerNotQuiescent` 并把 `installerExited` / `activeProcesses` 带进错误信息。
**成功和失败退出码走同一条收敛判定**，不因为退出码是 0 就放松。

这正是它自己在第一轮标为「P0 未全完成」的那条能力缺口，现在闭合了。

配套两条测试：父进程退出但后代仍在 → runner 保持阻塞直到 `ActiveProcesses=0`；
后代主动请求 `CREATE_BREAKAWAY_FROM_JOB` → 被拒绝（access denied）。
**两条都明确标注是进程模拟器场景，不是真实 NSIS 验收**——和第一轮口径一致。

## 三、残留

### W6-R5 🟡 race 工具链在 `E:/tmp`，是一次性的

`E:/tmp/hq-w6-toolchain/llvm-mingw-20260826-ucrt-x86_64/` 是便携解压的，
没进 PATH 也没进仓库。**下次谁想复现 `-race` 都得重新下一遍**，
而 `E:/tmp` 正是我们几轮一直在清的目录（和 W6-R3 的测试私钥同一个问题）。

至少要在 `packages/updatekit/README.md` 里写清：跑 `-race` 需要什么工具链、
从哪下、SHA256 是多少。交接单里有，但交接单是一次性文档，会被下一轮覆盖。

### 第一轮的 4 条残留状态

- **W6-R1（`-race` 没跑过）**：✅ 本轮关闭。
- **W6-R2（协议 0.1.0，只用临时 modfile 验过）**：✅ 本轮关闭，真合并了。
  但注意：**它合的是我改协议之前的 main**，现在主干已是 `0.2.1`（FZ-2.1）。
  W6 三个模块对 `RoleId` 零命中，`AgentTaskSpec` 也不用，所以不受 FZ-2.1 影响，
  下次合并自然带上。
- **W6-R3（测试私钥在 `E:/tmp`）**：❌ 未处理，本轮没派。
- **W6-R4（`acceptance/*.txt` 入库）**：❌ 未处理，且本轮又加了
  `round2-final-checks.txt`。

### 交接单第 3 节剩余 8 条

第 2、3、4、6、7、8、9、10 条保持未完成，本轮没派也没做。其中：

- 第 2 条（真实 NSIS + 代码签名 E2E）**需要你提供**：makensis、HQAgent 测试代码
  签名证书、signtool。这是外部资源，不是能力问题。
- 第 3、6 条（W1/W5 联调、健康检查期的 Worker Gate）要等 integration 起来。
- 第 4 条（events 投递）**卡在我这**：私有事件包络还没冻结。W6 明确说了
  「不自行选择 SSE 还是 NDJSON」，这个决定得我来做。
