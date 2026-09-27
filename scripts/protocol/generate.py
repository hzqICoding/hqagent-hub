#!/usr/bin/env python3
"""HQAgent-Hub 协议代码生成器（W0）。

单一事实源：
    packages/protocol/VERSION      协议版本
    packages/protocol/registry/    roles / capabilities / error-codes
    packages/protocol/schema/      JSON Schema draft 2020-12 子集

生成产物（全部禁止手改）：
    packages/protocol/generated/ts/       前端与 Tauri 使用的边界 DTO
    packages/protocol/generated/python/   Local Hub 使用的 pydantic v2 边界 DTO
    packages/protocol/generated/go/       Update Agent / Updater 使用的边界 DTO

工具链约定（对应分工方案 §5.1「必须固定工具及版本」）：
本生成器是自带的、随仓库版本化的固定工具，除 PyYAML 外零第三方依赖。
选择自建而不是 datamodel-code-generator / json-schema-to-typescript，
是因为 CI 要执行 `generate + git diff --exit-code`：外部生成器的版本漂移
会让同一份 Schema 在不同机器上产出不同文本，从而把这条门禁变成噪音。
代价是只支持本仓库实际用到的 Schema 子集，见 SUPPORTED 说明。

SUPPORTED（本生成器支持的 Schema 子集）：
    - type: object + properties + required + additionalProperties: false
    - type: string/integer/number/boolean，string 可带 enum / format / pattern / const
    - type: number + enum（数值字面量联合）
    - type: array + items（$ref 或原子类型）
    - $ref: "<file>.json#/$defs/<Name>" 或 "#/$defs/<Name>"
    - x-registry: 值域来自 registry/*.yaml，生成为字面量联合/枚举
    - x-generic-params / x-generic: 泛型容器（ApiEnvelope<T>、PageResult<T>、HubEvent<T>）
    - x-extends: 继承（TS extends / Python 基类）
    - x-map-value / x-map-value-primitive: Record<string, X>
    - x-go: 该类型同时生成 Go 版本
支持 oneOf 的 TypeScript/Python 联合与显式 null；Go远程联合未启用。
不支持 anyOf/allOf/条件校验。x-wire-strict 仅对新远程DTO启用字段边界检查。
"""

from __future__ import annotations

import json
import keyword
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("需要 PyYAML：python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyyaml")

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "packages" / "protocol"
SCHEMA_DIR = PROTOCOL / "schema"
REGISTRY_DIR = PROTOCOL / "registry"
OUT = PROTOCOL / "generated"

BANNER_LINES = [
    "此文件由 scripts/protocol/generate.py 生成，请勿手改。",
    "改协议请改 packages/protocol/schema/ 或 registry/，然后重新运行:",
    "    pwsh scripts/protocol/generate.ps1",
]

PRIMITIVES = {
    "string": ("string", "str", "string"),
    "integer": ("number", "int", "int64"),
    "number": ("number", "float", "float64"),
    "boolean": ("boolean", "bool", "bool"),
}


# --------------------------------------------------------------------------
# 载入
# --------------------------------------------------------------------------
def load_registries() -> dict:
    roles = yaml.safe_load((REGISTRY_DIR / "roles.yaml").read_text(encoding="utf-8"))
    caps = yaml.safe_load((REGISTRY_DIR / "capabilities.yaml").read_text(encoding="utf-8"))
    errs = yaml.safe_load((REGISTRY_DIR / "error-codes.yaml").read_text(encoding="utf-8"))
    return {
        "roles": [r["id"] for r in roles["roles"]],
        "capabilities": [c["id"] for c in caps["capabilities"]],
        "error-codes": [e["code"] for e in errs["errors"]],
        "_roles_full": roles,
        "_caps_full": caps,
        "_errs_full": errs,
    }


def load_schemas() -> dict:
    """返回 {typeName: {"file":…, "def":…}}，并检查全局类型名唯一。"""
    index: dict[str, dict] = {}
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for name, definition in doc.get("$defs", {}).items():
            if name in index:
                raise SystemExit(
                    f"类型名冲突：{name} 同时出现在 {index[name]['file']} 和 {path.name}。"
                    "生成器要求全局唯一的类型名。"
                )
            index[name] = {"file": path.name, "def": definition, "order": path.name}
    return index


# --------------------------------------------------------------------------
# 类型解析
# --------------------------------------------------------------------------
REF_RE = re.compile(r"^(?:([\w.-]+\.json))?#/\$defs/(\w+)$")


def ref_name(ref: str) -> str:
    m = REF_RE.match(ref)
    if not m:
        raise SystemExit(f"不支持的 $ref 形式：{ref}")
    return m.group(2)


def is_alias(definition: dict) -> bool:
    """标量别名：string/number 且没有 properties。"""
    return definition.get("type") in PRIMITIVES and "properties" not in definition


def deps_of(definition: dict) -> set[str]:
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                found.add(ref_name(node["$ref"]))
            for key, value in node.items():
                if key in ("x-map-value",):
                    found.add(ref_name(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(definition)
    if "x-extends" in definition:
        found.add(definition["x-extends"])
    return found


def topo_sort(index: dict) -> list[str]:
    """按依赖排序，保证 Python 基类先于子类定义。"""
    ordered: list[str] = []
    seen: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str):
        if name in seen or name not in index:
            return
        if name in visiting:  # 循环引用：交给 from __future__ import annotations 处理
            return
        visiting.add(name)
        for dep in sorted(deps_of(index[name]["def"])):
            visit(dep)
        visiting.discard(name)
        seen.add(name)
        ordered.append(name)

    for name in sorted(index):
        visit(name)
    return ordered


class Emitter:
    """把一个 property 的 schema 片段翻译成三种语言的类型表达式。"""

    def __init__(self, index: dict, registries: dict, lang: int):
        self.index = index
        self.registries = registries
        self.lang = lang  # 0=ts 1=py 2=go

    def literal(self, value) -> str:
        if isinstance(value, str):
            return f"'{value}'" if self.lang == 0 else f'"{value}"'
        if isinstance(value, bool):
            return {0: "true", 1: "True", 2: "true"}[self.lang] if value else {0: "false", 1: "False", 2: "false"}[self.lang]
        return repr(value)

    def union(self, values: list) -> str:
        parts = [self.literal(v) for v in values]
        if self.lang == 0:
            return " | ".join(parts)
        if self.lang == 1:
            return "Literal[" + ", ".join(parts) + "]"
        return "string"

    def expr(self, node: dict, owner: str = "") -> str:
        if "oneOf" in node:
            if self.lang == 2:
                raise SystemExit("oneOf is not supported for Go consumers")
            return " | ".join(self.expr(branch, owner) for branch in node["oneOf"])
        if node.get("type") == "null":
            return {0: "null", 1: "None", 2: "any"}[self.lang]
        if "$ref" in node:
            return self.named(ref_name(node["$ref"]))
        if "x-generic" in node:
            return node["x-generic"] if self.lang == 0 else ("Any" if self.lang == 1 else "json.RawMessage")
        if "x-map-value" in node:
            inner = self.named(ref_name(node["x-map-value"]))
            return {0: f"Record<string, {inner}>", 1: f"dict[str, {inner}]", 2: f"map[string]{inner}"}[self.lang]
        if "x-map-value-primitive" in node:
            inner = PRIMITIVES[node["x-map-value-primitive"]][self.lang]
            return {0: f"Record<string, {inner}>", 1: f"dict[str, {inner}]", 2: f"map[string]{inner}"}[self.lang]
        if "const" in node:
            return self.union([node["const"]]) if self.lang != 2 else PRIMITIVES[node.get("type", "string")][2]
        node_type = node.get("type")
        if node_type == "array":
            item = node.get("items", {"type": "string"})
            inner = self.expr(item, owner)
            if self.lang == 1 and self.index.get(owner, {}).get("def", {}).get("x-wire-strict") and item.get("type") in ("integer", "string", "boolean") and "enum" not in item and "const" not in item:
                constraints = ["strict=True"]
                for source, target in (("minimum", "ge"), ("maximum", "le"), ("minLength", "min_length"), ("maxLength", "max_length"), ("pattern", "pattern")):
                    if source in item:
                        constraints.append(f"{target}={item[source]!r}")
                inner = f"Annotated[{inner}, Field({', '.join(constraints)})]"
            return {0: f"({inner})[]" if " | " in inner else f"{inner}[]", 1: f"list[{inner}]", 2: f"[]{inner}"}[self.lang]
        if node_type == "object" and "properties" not in node:
            return {0: "Record<string, unknown>", 1: "dict[str, Any]", 2: "map[string]any"}[self.lang]
        if "enum" in node:
            return self.union(node["enum"])
        if node_type in PRIMITIVES:
            return PRIMITIVES[node_type][self.lang]
        return {0: "unknown", 1: "Any", 2: "any"}[self.lang]

    def named(self, name: str) -> str:
        if name not in self.index:
            raise SystemExit(f"引用了未定义的类型：{name}")
        return name


# --------------------------------------------------------------------------
# 输出：通用
# --------------------------------------------------------------------------
def banner(comment: str) -> str:
    return "\n".join(f"{comment} {line}" for line in BANNER_LINES)


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def py_member(value) -> str:
    """把枚举值变成合法的 Python 标识符。

    枚举值里有连字符和点（hq-blue / zh-CN / windows-nsis / 0.9），
    直接 upper() 会生成非法标识符。
    """
    ident = re.sub(r"[^0-9a-zA-Z]+", "_", str(value)).strip("_")
    ident = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", ident).upper()
    return f"V_{ident}" if not ident or ident[0].isdigit() else ident


def registry_values(definition: dict, registries: dict) -> list[str] | None:
    key = definition.get("x-registry")
    if not key:
        return None
    # x-registry-open: 值域「以 registry 为内置集合，但允许用户扩展」。
    # 生成闭枚举会让自定义值进不了 DTO（裁决 D30：RoleId 就是这么被卡住的），
    # 所以这类返回 None，走下面的 str 别名分支；内置值另出常量表。
    if definition.get("x-registry-open"):
        return None
    return registries[key] if key else None


def is_open_registry(definition: dict) -> bool:
    return bool(definition.get("x-registry") and definition.get("x-registry-open"))


# --------------------------------------------------------------------------
# 输出：TypeScript
# --------------------------------------------------------------------------
def emit_ts(index: dict, registries: dict, order: list[str], version: str) -> str:
    em = Emitter(index, registries, 0)
    out = [banner("//"), "", f"export const PROTOCOL_VERSION = '{version}' as const", ""]

    for name in order:
        d = index[name]["def"]
        desc = d.get("description")
        if desc:
            out.append(f"/** {desc} */")
        if "oneOf" in d:
            out.append(f"export type {name} = {em.expr(d, name)}")
            out.append("")
            continue
        values = registry_values(d, registries)
        if values is not None:
            out.append(f"export type {name} =")
            out.extend(f"  | '{v}'" for v in values)
            out.append("")
            continue
        if is_open_registry(d):
            builtin = registries[d["x-registry"]]
            out.append(f"export type {name} = string")
            out.append("")
            const = "BUILTIN_" + snake(name).upper() + "S"
            out.append(f"export const {const} = [")
            out.extend(f"  '{v}'," for v in builtin)
            out.append("] as const")
            out.append("")
            continue
        if "enum" in d and "properties" not in d:
            out.append(f"export type {name} =")
            out.extend(f"  | {em.literal(v)}" for v in d["enum"])
            out.append("")
            continue
        if is_alias(d):
            out.append(f"export type {name} = {PRIMITIVES[d['type']][0]}")
            out.append("")
            continue
        generics = d.get("x-generic-params")
        head = f"export interface {name}"
        if generics:
            head += "<" + ", ".join(f"{g} = unknown" for g in generics) + ">"
        if "x-extends" in d:
            head += f" extends {d['x-extends']}"
        out.append(head + " {")
        required = set(d.get("required", []))
        for prop, node in d.get("properties", {}).items():
            pdesc = node.get("description")
            if pdesc:
                out.append(f"  /** {pdesc} */")
            optional = "" if prop in required else "?"
            out.append(f"  {prop}{optional}: {em.expr(node, name)}")
        out.append("}")
        out.append("")

    # registry 元数据常量，UI 直接用它渲染角色名和错误提示
    roles = registries["_roles_full"]["roles"]
    out.append("export const BUILTIN_ROLES = [")
    for r in roles:
        out.append(f"  {{ id: '{r['id']}', displayName: '{r['displayName']}', description: '{r['description']}' }},")
    out.append("] as const")
    out.append("")
    out.append("export const DANGEROUS_ACTIONS = [")
    for a in registries["_roles_full"]["dangerousActions"]:
        out.append(f"  '{a}',")
    out.append("] as const")
    out.append("")
    errs = registries["_errs_full"]["errors"]
    out.append("export const ERROR_CATALOG: Record<ErrorCode, { http: number; retryable: boolean }> = {")
    for e in errs:
        out.append(f"  {e['code']}: {{ http: {e['http']}, retryable: {str(e['retryable']).lower()} }},")
    out.append("}")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# 输出：Python (pydantic v2)
# --------------------------------------------------------------------------
def emit_py(index: dict, registries: dict, order: list[str], version: str) -> str:
    em = Emitter(index, registries, 1)
    out = [
        '"""' + BANNER_LINES[0] + '"""',
        "",
        "from __future__ import annotations",
        "",
        "from enum import StrEnum",
        "from typing import Annotated, Any, Literal",
        "",
        "from pydantic import BaseModel, ConfigDict, Field, RootModel, model_serializer, model_validator",
        "",
        f'PROTOCOL_VERSION = "{version}"',
        "",
        "",
        "class _Base(BaseModel):",
        "    \"\"\"边界 DTO 基类：线上字段是 camelCase，Python 侧用 snake_case 访问。\"\"\"",
        "",
        "    model_config = ConfigDict(populate_by_name=True, extra=\"forbid\")",
        "",
    ]

    if any(item["def"].get("x-wire-strict") for item in index.values()):
        out.extend([
            "", "class _RemoteBase(_Base):",
            '    """R1 wire DTOs: omitted optional fields are allowed; explicit null is opt-in."""',
            "", '    @model_validator(mode="before")', "    @classmethod",
            "    def _check_wire_scalars(cls, value):",
            "        if isinstance(value, dict):",
            "            by_alias = {field.alias: field for field in cls.model_fields.values()}",
            "            for key, item in value.items():",
            "                field = by_alias.get(key) or cls.model_fields.get(key)",
            "                if field is None:", "                    continue",
            "                rules = field.json_schema_extra or {}",
            '                if item is None and not rules.get("wireNullable"):',
            '                    raise ValueError(f"{key} must be omitted rather than null")',
            '                if rules.get("wireType") == "boolean" and not isinstance(item, bool):',
            '                    raise ValueError(f"{key} must be a boolean")',
            '                if rules.get("wireType") == "integer" and (not isinstance(item, int) or isinstance(item, bool)):',
            '                    raise ValueError(f"{key} must be an integer")',
            "        return value", "",
            '    @model_serializer(mode="wrap")',
            "    def _serialize_wire(self, handler, info):",
            "        data = handler(self)",
            "        for name, field in type(self).model_fields.items():",
            '            if not (field.json_schema_extra or {}).get("wireNullable") or getattr(self, name) is not None:',
            "                continue",
            "            if info.exclude and name in info.exclude:", "                continue",
            "            if info.include is not None and name not in info.include:", "                continue",
            "            if field.is_required() or name in self.model_fields_set:",
            "                data[field.alias if info.by_alias else name] = None",
            "        return data", "",
        ])
    def union_expr(node):
        if "$ref" in node:
            definition = index[ref_name(node["$ref"])]["def"]
            if "oneOf" in definition:
                return union_expr(definition)
        if "oneOf" in node:
            return " | ".join(union_expr(branch) for branch in node["oneOf"])
        return em.expr(node)
    for name in order:
        d = index[name]["def"]
        if "oneOf" in d:
            out.extend(["", f"class {name}(RootModel[{union_expr(d)}]):", "    pass", ""])
            continue
        values = registry_values(d, registries)
        if values is not None:
            out.append("")
            out.append(f"class {name}(StrEnum):")
            for v in values:
                out.append(f'    {py_member(v)} = "{v}"')
            out.append("")
            continue
        if is_open_registry(d):
            builtin = registries[d["x-registry"]]
            out.append("")
            out.append(f"class Builtin{name}(StrEnum):")
            out.append(f'    """内置{name}值。边界类型是 str，自定义值同样合法（裁决 D30）。"""')
            out.append("")
            for v in builtin:
                out.append(f'    {py_member(v)} = "{v}"')
            out.append("")
            out.append(f"{name} = str")
            out.append("")
            continue
        if "enum" in d and "properties" not in d:
            if d.get("type") == "string":
                out.append("")
                out.append(f"class {name}(StrEnum):")
                for v in d["enum"]:
                    out.append(f'    {py_member(v)} = "{v}"')
                if d.get("x-wire-strict"):
                    # Strict scalar boundary DTOs support the same fixture API as
                    # object DTOs without wrapping or changing the wire value.
                    out.extend([
                        "", "    @classmethod",
                        "    def model_validate(cls, value):",
                        "        from pydantic import TypeAdapter",
                        "        return TypeAdapter(cls).validate_python(value)",
                        "", "    def model_dump(self, **kwargs):",
                        "        return self.value",
                    ])
                out.append("")
            else:
                out.append("")
                out.append(f"{name} = {em.union(d['enum'])}")
                out.append("")
            continue
        if is_alias(d):
            out.append("")
            out.append(f"{name} = {PRIMITIVES[d['type']][1]}")
            out.append("")
            continue

        base = d.get("x-extends", "_RemoteBase" if d.get("x-wire-strict") else "_Base")
        out.append("")
        out.append(f"class {name}({base}):")
        desc = d.get("description")
        if desc:
            out.append(f'    """{desc}"""')
            out.append("")
        props = d.get("properties", {})
        if not props:
            out.append("    pass")
            out.append("")
            continue
        required = set(d.get("required", []))
        for prop, node in props.items():
            attr = snake(prop)
            # from / in / class 之类是 Python 关键字；model_ 前缀会和 pydantic 保留命名空间冲突。
            # 线上字段名不变，只改 Python 侧属性名，由 alias 兜住。
            if keyword.iskeyword(attr) or attr.startswith("model_"):
                attr += "_"
            expr = em.expr(node, name)
            if d.get("x-wire-strict"):
                options = [f'alias="{prop}"']
                if prop not in required:
                    expr += " | None"
                    options.insert(0, "default=None")
                for schema_key, field_key in (("minLength", "min_length"), ("maxLength", "max_length"),
                    ("minimum", "ge"), ("maximum", "le"), ("minItems", "min_length"), ("maxItems", "max_length"),
                    ("pattern", "pattern")):
                    if schema_key in node:
                        options.append(f"{field_key}={node[schema_key]!r}")
                if node.get("type") in ("string", "integer", "number", "boolean") and "const" not in node and "enum" not in node:
                    options.append("strict=True")
                rules = {"wireNullable": any(branch.get("type") == "null" for branch in node.get("oneOf", [])),
                         "wireType": node.get("type")}
                options.append(f"json_schema_extra={rules!r}")
                out.append(f"    {attr}: {expr} = Field({', '.join(options)})")
            elif prop in required:
                out.append(f'    {attr}: {expr} = Field(alias="{prop}")')
            else:
                out.append(f'    {attr}: {expr} | None = Field(default=None, alias="{prop}")')
        out.append("")

    out.append("")
    out.append("ERROR_CATALOG: dict[str, dict[str, Any]] = {")
    for e in registries["_errs_full"]["errors"]:
        out.append(f'    "{e["code"]}": {{"http": {e["http"]}, "retryable": {e["retryable"]}}},')
    out.append("}")
    out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
# 输出：Go（只生成 x-go 标记的类型及其依赖）
# --------------------------------------------------------------------------
def go_closure(index: dict) -> list[str]:
    wanted: set[str] = {n for n, v in index.items() if v["def"].get("x-go")}
    changed = True
    while changed:
        changed = False
        for name in list(wanted):
            for dep in deps_of(index[name]["def"]):
                if dep in index and dep not in wanted:
                    wanted.add(dep)
                    changed = True
    return [n for n in topo_sort(index) if n in wanted]


def go_name(prop: str) -> str:
    return prop[:1].upper() + prop[1:]


def emit_go(index: dict, registries: dict, version: str) -> str:
    em = Emitter(index, registries, 2)
    names = go_closure(index)
    # 常量名不能叫 ProtocolVersion：schema 里已有同名类型别名，Go 不允许重名。
    out = [banner("//"), "", "package protocol", "", 'import "encoding/json"', "",
           f'const Version = "{version}"', ""]

    for name in names:
        d = index[name]["def"]
        if "oneOf" in d:
            raise SystemExit("oneOf is not supported for Go consumers")
        values = registry_values(d, registries)
        if values is not None or ("enum" in d and "properties" not in d):
            vals = values if values is not None else [str(v) for v in d["enum"]]
            out.append(f"type {name} string")
            out.append("")
            out.append("const (")
            for v in vals:
                ident = name + "".join(part.capitalize() for part in re.split(r"[-_]", str(v)))
                out.append(f'\t{ident} {name} = "{v}"')
            out.append(")")
            out.append("")
            continue
        if is_alias(d):
            out.append(f"type {name} = {PRIMITIVES[d['type']][2]}")
            out.append("")
            continue
        out.append(f"type {name} struct {{")
        required = set(d.get("required", []))
        for prop, node in d.get("properties", {}).items():
            expr = em.expr(node, name)
            tag = prop if prop in required else f"{prop},omitempty"
            pointer = "" if prop in required or expr.startswith(("[]", "map[")) else "*"
            if expr == "json.RawMessage":
                pointer = ""
            out.append(f'\t{go_name(prop)} {pointer}{expr} `json:"{tag}"`')
        out.append("}")
        out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------
def main() -> int:
    version = (PROTOCOL / "VERSION").read_text(encoding="utf-8").strip()
    registries = load_registries()
    index = load_schemas()
    order = topo_sort(index)

    (OUT / "ts").mkdir(parents=True, exist_ok=True)
    (OUT / "python").mkdir(parents=True, exist_ok=True)
    (OUT / "go").mkdir(parents=True, exist_ok=True)

    (OUT / "ts" / "index.ts").write_text(emit_ts(index, registries, order, version), encoding="utf-8", newline="\n")
    (OUT / "python" / "__init__.py").write_text(
        '"""HQAgent-Hub 协议边界 DTO（生成物）。"""\n\nfrom .models import *  # noqa: F401,F403\n',
        encoding="utf-8",
        newline="\n",
    )
    (OUT / "python" / "models.py").write_text(emit_py(index, registries, order, version), encoding="utf-8", newline="\n")
    (OUT / "go" / "protocol.go").write_text(emit_go(index, registries, version), encoding="utf-8", newline="\n")
    # go.mod 一并生成，保证 generated/go 是可独立编译的模块：
    # HQUpdateKit 与 apps/update-agent 通过 replace 指向本目录消费它。
    (OUT / "go" / "go.mod").write_text(
        "// 此文件由 scripts/protocol/generate.py 生成，请勿手改。\n"
        "module hqagent.local/protocol\n\ngo 1.26\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"protocol {version}: 生成 {len(index)} 个类型 -> ts / python / go")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
