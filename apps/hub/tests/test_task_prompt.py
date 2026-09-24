from adapters.prompt import build_task_prompt
from adapters.tests.test_contract_rules import task_spec


def test_task_prompt_states_actual_read_boundary_and_default_output_language(tmp_path):
    spec = task_spec(tmp_path).model_copy(update={"read_only": True})
    prompt = build_task_prompt(spec)
    assert f"本轮授权根目录（实际工作目录）：{spec.worktree_path}" in prompt
    assert "引用外部目录不代表获得访问授权" in prompt
    assert "默认使用简体中文" in prompt
    assert "用户明确要求其他语言时按用户要求" in prompt
    assert "只读，禁止修改文件" in prompt
    assert "AgentResult JSON Schema" in prompt
