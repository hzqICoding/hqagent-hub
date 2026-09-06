from __future__ import annotations

from protocol.generated.python import AgentTaskSpec


def build_task_prompt(spec: AgentTaskSpec) -> str:
    lines = [
        "你正在执行 HQAgent-Hub 分派的隔离任务。",
        f"目标：{spec.objective}",
        f"角色：{str(spec.role_id)}",
        f"会话用途：{spec.session_purpose.value}",
        "只允许修改这些 glob：",
        *(f"- {item}" for item in spec.allowed_paths),
    ]
    if spec.read_first:
        lines.extend(["开工前按顺序读取：", *(f"- {item}" for item in spec.read_first)])
    if spec.handoff_documents:
        lines.extend(["上游 handoff：", *(f"- {item}" for item in spec.handoff_documents)])
    if spec.acceptance:
        lines.extend(["验收命令：", *(f"- {item}" for item in spec.acceptance)])
    lines.extend(
        [
            "不得切换到仓库主目录；工作目录就是当前 worktree。",
            "最后必须只返回符合给定 AgentResult JSON Schema 的对象。",
        ]
    )
    return "\n".join(lines)
