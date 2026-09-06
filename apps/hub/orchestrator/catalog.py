from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    hard: bool
    display_name: str


@dataclass(frozen=True, slots=True)
class RolePermissionDefinition:
    filesystem: str
    shell: bool
    can_approve: bool
    can_merge: bool
    writable_paths: tuple[str, ...]
    requires_approval: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    role_id: str
    display_name: str
    required_capabilities: frozenset[str]
    preferred_capabilities: frozenset[str]
    permissions: RolePermissionDefinition


@dataclass(frozen=True, slots=True)
class BuiltinCatalog:
    roles: Mapping[str, RoleDefinition]
    capabilities: Mapping[str, CapabilityDefinition]
    dangerous_actions: frozenset[str]

    @classmethod
    def load(cls) -> "BuiltinCatalog":
        protocol_root = files("protocol")
        roles_raw = _parse_yaml_subset(
            protocol_root.joinpath("registry/roles.yaml").read_text(encoding="utf-8")
        )
        capabilities_raw = _parse_yaml_subset(
            protocol_root.joinpath("registry/capabilities.yaml").read_text(encoding="utf-8")
        )

        capabilities = {
            item["id"]: CapabilityDefinition(
                capability_id=item["id"],
                hard=bool(item["hard"]),
                display_name=item["displayName"],
            )
            for item in capabilities_raw["capabilities"]
        }
        roles = {}
        for item in roles_raw["roles"]:
            raw_permissions = item["permissions"]
            role = RoleDefinition(
                role_id=item["id"],
                display_name=item["displayName"],
                required_capabilities=frozenset(item.get("requiredCapabilities", [])),
                preferred_capabilities=frozenset(item.get("preferredCapabilities", [])),
                permissions=RolePermissionDefinition(
                    filesystem=raw_permissions["filesystem"],
                    shell=bool(raw_permissions["shell"]),
                    can_approve=bool(raw_permissions["canApprove"]),
                    can_merge=bool(raw_permissions["canMerge"]),
                    writable_paths=tuple(raw_permissions.get("writablePaths", [])),
                    requires_approval=tuple(raw_permissions.get("requiresApproval", [])),
                ),
            )
            roles[role.role_id] = role
        return cls(
            roles=roles,
            capabilities=capabilities,
            dangerous_actions=frozenset(roles_raw["dangerousActions"]),
        )

    def role(self, role_id: str) -> RoleDefinition:
        try:
            return self.roles[role_id]
        except KeyError as exc:
            raise KeyError(f"未注册角色：{role_id}") from exc

    def hard_capabilities(self, capability_ids: set[str] | frozenset[str]) -> frozenset[str]:
        return frozenset(
            capability_id
            for capability_id in capability_ids
            if self.capabilities.get(capability_id)
            and self.capabilities[capability_id].hard
        )


def _strip_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
            continue
        if character == "#" and quote is None:
            return line[:index]
    return line


def _split_inline(value: str) -> list[str]:
    content = value[1:-1].strip()
    if not content:
        return []
    result: list[str] = []
    quote: str | None = None
    start = 0
    for index, character in enumerate(content):
        if character in {"'", '"'}:
            if quote == character:
                quote = None
            elif quote is None:
                quote = character
        elif character == "," and quote is None:
            result.append(content[start:index].strip())
            start = index + 1
    result.append(content[start:].strip())
    return result


def _scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return None
    if value.startswith("[") and value.endswith("]"):
        return [_scalar(item) for item in _split_inline(value)]
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _split_key_value(content: str) -> tuple[str, str]:
    key, separator, value = content.partition(":")
    if not separator or not key.strip():
        raise ValueError(f"不支持的 YAML 行：{content}")
    return key.strip(), value.strip()


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the dependency-free YAML subset used by the frozen registries."""

    tokens: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2:
            raise ValueError("registry YAML indentation must use two spaces")
        tokens.append((indent, line.lstrip()))

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens) or tokens[index][0] < indent:
            return {}, index
        is_list = tokens[index][0] == indent and tokens[index][1].startswith("- ")
        container: Any = [] if is_list else {}

        while index < len(tokens):
            current_indent, content = tokens[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"unexpected indentation near: {content}")

            if is_list:
                if not content.startswith("- "):
                    break
                item_text = content[2:].strip()
                if not item_text:
                    item, index = parse_block(index + 1, indent + 2)
                    container.append(item)
                    continue
                if ":" in item_text:
                    key, raw_value = _split_key_value(item_text)
                    item = {key: _scalar(raw_value)}
                    index += 1
                    if index < len(tokens) and tokens[index][0] > indent:
                        child, index = parse_block(index, indent + 2)
                        if not isinstance(child, dict):
                            raise ValueError("mapping list item must contain a mapping")
                        item.update(child)
                    container.append(item)
                    continue
                container.append(_scalar(item_text))
                index += 1
                continue

            if content.startswith("- "):
                break
            key, raw_value = _split_key_value(content)
            index += 1
            if raw_value:
                container[key] = _scalar(raw_value)
            elif index < len(tokens) and tokens[index][0] > indent:
                child, index = parse_block(index, indent + 2)
                container[key] = child
            else:
                container[key] = {}
        return container, index

    parsed, final_index = parse_block(0, 0)
    if final_index != len(tokens) or not isinstance(parsed, dict):
        raise ValueError("registry YAML contains unsupported syntax")
    return parsed
