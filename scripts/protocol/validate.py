#!/usr/bin/env python3
"""HQAgent-Hub 协议校验器（W0）。

做四件事：
    1. 结构自检     —— $ref 可解析、类型名全局唯一、x-registry 键存在、x-extends 存在
    2. Fixture 校验 —— fixtures/contracts/ 下每个原子 Fixture 对照 manifest 指定的类型校验
    3. 生成物漂移   —— --check-generated 重新生成到临时目录并逐字节比对
    4. 注册表自检   —— 角色引用的能力必须在能力表里，requiresApproval 必须是 dangerousActions 子集

零第三方依赖（除 PyYAML）。只实现本仓库 Schema 子集所需的校验，
不追求成为通用 JSON Schema 实现——通用实现请用外部工具，那不是这里的目标。
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("需要 PyYAML：python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyyaml")

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "packages" / "protocol"
SCHEMA_DIR = PROTOCOL / "schema"
REGISTRY_DIR = PROTOCOL / "registry"
FIXTURES = PROTOCOL / "fixtures" / "contracts"

REF_RE = re.compile(r"^(?:([\w.-]+\.json))?#/\$defs/(\w+)$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")

errors: list[str] = []


def fail(where: str, message: str) -> None:
    errors.append(f"{where}: {message}")


def load_index() -> tuple[dict, dict]:
    index: dict[str, dict] = {}
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for name, definition in doc.get("$defs", {}).items():
            if name in index:
                fail(path.name, f"类型名 {name} 重复定义")
            index[name] = definition
    registries = {
        "roles": [r["id"] for r in yaml.safe_load((REGISTRY_DIR / "roles.yaml").read_text(encoding="utf-8"))["roles"]],
        "capabilities": [
            c["id"] for c in yaml.safe_load((REGISTRY_DIR / "capabilities.yaml").read_text(encoding="utf-8"))["capabilities"]
        ],
        "error-codes": [
            e["code"] for e in yaml.safe_load((REGISTRY_DIR / "error-codes.yaml").read_text(encoding="utf-8"))["errors"]
        ],
    }
    return index, registries


# ---------------------------------------------------------------- 结构自检
def check_structure(index: dict, registries: dict) -> None:
    def walk(node, where: str):
        if isinstance(node, dict):
            if "oneOf" in node:
                branches = node["oneOf"]
                if not isinstance(branches, list) or len(branches) < 2:
                    fail(where, "oneOf requires at least two branches")
                elif any(not isinstance(branch, dict) or not (
                    ("$ref" in branch and set(branch) <= {"$ref", "description"})
                    or branch == {"type": "null"}
                ) for branch in branches):
                    fail(where, "oneOf supports named refs or explicit null only")
            if "$ref" in node:
                m = REF_RE.match(node["$ref"])
                if not m:
                    fail(where, f"不支持的 $ref 形式 {node['$ref']}")
                elif m.group(2) not in index:
                    fail(where, f"$ref 指向未定义类型 {m.group(2)}")
            if "x-registry" in node and node["x-registry"] not in registries:
                fail(where, f"x-registry 未知键 {node['x-registry']}")
            if "x-map-value" in node:
                m = REF_RE.match(node["x-map-value"])
                if not m or m.group(2) not in index:
                    fail(where, f"x-map-value 指向未定义类型 {node['x-map-value']}")
            for key, value in node.items():
                if key not in ("$ref", "x-map-value"):
                    walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for name, definition in index.items():
        walk(definition, name)
        parent = definition.get("x-extends")
        if parent and parent not in index:
            fail(name, f"x-extends 指向未定义类型 {parent}")
        if definition.get("type") == "object" and "properties" in definition:
            if definition.get("additionalProperties") is not False:
                fail(name, "对象类型必须显式写 additionalProperties: false")
            for req in definition.get("required", []):
                if req not in definition["properties"]:
                    fail(name, f"required 里的 {req} 不在 properties 中")


# ---------------------------------------------------------------- 注册表自检
def check_registries() -> None:
    roles_doc = yaml.safe_load((REGISTRY_DIR / "roles.yaml").read_text(encoding="utf-8"))
    caps = {c["id"] for c in yaml.safe_load((REGISTRY_DIR / "capabilities.yaml").read_text(encoding="utf-8"))["capabilities"]}
    dangerous = set(roles_doc["dangerousActions"])
    for role in roles_doc["roles"]:
        for cap in role.get("requiredCapabilities", []) + role.get("preferredCapabilities", []):
            if cap not in caps:
                fail(f"roles.yaml/{role['id']}", f"引用了未定义能力 {cap}")
        for action in role["permissions"].get("requiresApproval", []):
            if action not in dangerous:
                fail(f"roles.yaml/{role['id']}", f"requiresApproval 里的 {action} 不在 dangerousActions 中")
        perms = role["permissions"]
        if perms["filesystem"] == "read_only" and perms["writablePaths"]:
            fail(f"roles.yaml/{role['id']}", "read_only 角色不应声明 writablePaths")


# ---------------------------------------------------------------- 实例校验
def resolve(node: dict, index: dict) -> dict:
    if "$ref" in node:
        m = REF_RE.match(node["$ref"])
        return index.get(m.group(2), {}) if m else {}
    return node


def merged_properties(definition: dict, index: dict) -> tuple[dict, set]:
    props = dict(definition.get("properties", {}))
    required = set(definition.get("required", []))
    parent = definition.get("x-extends")
    if parent and parent in index:
        pprops, preq = merged_properties(index[parent], index)
        props = {**pprops, **props}
        required |= preq
    return props, required


def validate_value(value, node: dict, index: dict, registries: dict, path: str) -> None:
    if "x-generic" in node:
        return  # 泛型载荷由具体事件类型各自约束，见事件字典
    node = resolve(node, index) if "$ref" in node else node

    if "oneOf" in node:
        matches = 0
        for branch in node["oneOf"]:
            start = len(errors)
            validate_value(value, branch, index, registries, path)
            matches += len(errors) == start
            del errors[start:]
        if matches != 1:
            fail(path, f"oneOf requires exactly one matching branch, got {matches}")
        return
    if node.get("type") == "null":
        if value is not None:
            fail(path, "must be null")
        return
    if "x-registry" in node:
        if not isinstance(value, str):
            fail(path, f"应为字符串，实际 {type(value).__name__}")
        elif value not in registries[node["x-registry"]]:
            fail(path, f"值 {value!r} 不在注册表 {node['x-registry']} 中")
        return
    if "const" in node and value != node["const"]:
        fail(path, f"应为常量 {node['const']!r}，实际 {value!r}")
        return
    if "enum" in node and "properties" not in node:
        if value not in node["enum"]:
            fail(path, f"值 {value!r} 不在枚举 {node['enum']} 中")
        return

    node_type = node.get("type")
    if node_type == "object":
        if not isinstance(value, dict):
            fail(path, f"应为对象，实际 {type(value).__name__}")
            return
        if "x-map-value" in node:
            target = resolve({"$ref": node["x-map-value"]}, index)
            for key, item in value.items():
                validate_value(item, target, index, registries, f"{path}.{key}")
            return
        if "x-map-value-primitive" in node or "properties" not in node:
            return
        props, required = merged_properties(node, index)
        for req in required:
            if req not in value:
                fail(path, f"缺少必填字段 {req}")
        if node.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    fail(path, f"出现未定义字段 {key}")
        for key, item in value.items():
            if key in props:
                validate_value(item, props[key], index, registries, f"{path}.{key}")
        return

    if node_type == "array":
        if not isinstance(value, list):
            fail(path, f"应为数组，实际 {type(value).__name__}")
            return
        if "minItems" in node and len(value) < node["minItems"]:
            fail(path, "fewer than minItems")
        if "maxItems" in node and len(value) > node["maxItems"]:
            fail(path, "more than maxItems")
        item_schema = node.get("items", {})
        for i, item in enumerate(value):
            validate_value(item, item_schema, index, registries, f"{path}[{i}]")
        return

    if node_type == "string":
        if not isinstance(value, str):
            fail(path, f"应为字符串，实际 {type(value).__name__}")
            return
        if node.get("format") == "date-time" and not DATETIME_RE.match(value):
            fail(path, f"不是合法 RFC3339 时间戳：{value!r}")
        if "pattern" in node and not re.match(node["pattern"], value):
            fail(path, f"不匹配 pattern {node['pattern']}：{value!r}")
        if "maxLength" in node and len(value) > node["maxLength"]:
            fail(path, f"length exceeds maxLength {node['maxLength']}")
        if "minLength" in node and len(value) < node["minLength"]:
            fail(path, f"长度小于 minLength {node['minLength']}")
        return

    if node_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            fail(path, f"应为整数，实际 {type(value).__name__}")
            return
    elif node_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            fail(path, f"应为数值，实际 {type(value).__name__}")
            return
    elif node_type == "boolean":
        if not isinstance(value, bool):
            fail(path, f"应为布尔，实际 {type(value).__name__}")
            return
    if node_type in ("integer", "number"):
        if "minimum" in node and value < node["minimum"]:
            fail(path, f"小于 minimum {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            fail(path, f"大于 maximum {node['maximum']}")


# ---------------------------------------------------------------- Fixtures
def check_fixtures(index: dict, registries: dict) -> int:
    manifest_path = FIXTURES / "manifest.json"
    if not manifest_path.exists():
        fail("fixtures", "缺少 manifest.json")
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declared = set(manifest["fixtures"])
    on_disk = {p.name for p in FIXTURES.glob("*.json") if p.name != "manifest.json"}
    for missing in sorted(declared - on_disk):
        fail("fixtures", f"manifest 声明了 {missing} 但文件不存在")
    for extra in sorted(on_disk - declared):
        fail("fixtures", f"{extra} 未登记进 manifest")
    for filename, type_name in manifest["fixtures"].items():
        path = FIXTURES / filename
        if not path.exists():
            continue
        if type_name not in index:
            fail(filename, f"manifest 指定的类型 {type_name} 未定义")
            continue
        instance = json.loads(path.read_text(encoding="utf-8"))
        validate_value(instance, index[type_name], index, registries, filename)
    return len(manifest["fixtures"])


# ---------------------------------------------------------------- 生成物漂移
def check_generated() -> None:
    import subprocess

    generated = PROTOCOL / "generated"
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "before"
        subprocess.run([sys.executable, "-c", "import shutil,sys; shutil.copytree(sys.argv[1], sys.argv[2])",
                        str(generated), str(backup)], check=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "protocol" / "generate.py")],
                       check=True, capture_output=True)
        for after in sorted(generated.rglob("*")):
            if after.is_dir():
                continue
            rel = after.relative_to(generated)
            before = backup / rel
            if not before.exists():
                fail("generated", f"{rel} 是新生成的，说明提交里缺文件")
            elif before.read_bytes() != after.read_bytes():
                fail("generated", f"{rel} 与重新生成的结果不一致，请提交生成物")


def main() -> int:
    index, registries = load_index()
    check_structure(index, registries)
    check_registries()
    count = check_fixtures(index, registries)
    if "--check-generated" in sys.argv:
        check_generated()

    if errors:
        print(f"协议校验失败，共 {len(errors)} 项：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"协议校验通过：{len(index)} 个类型，{count} 个 Contract Fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
