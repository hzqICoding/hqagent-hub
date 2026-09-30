from __future__ import annotations

import fnmatch
import re
import shutil
import os
import shlex
import hashlib
from pathlib import Path
from typing import Any, Iterable

from protocol.generated.python import FileChange


_ABSOLUTE_WINDOWS_PATH = re.compile(r"(?i)([a-z]:[\\/][^\s\"'|;&<>]+)")
_QUOTED_WINDOWS_PATH = re.compile(r'''(?i)(["'])([a-z]:[\\/][^\r\n]*?)\1''')
_POWERSHELL_LAUNCH = re.compile(
    r'^\s*"([^"]+)"\s+(?:(?:-NoProfile|-NoLogo|-NonInteractive)\s+)*-(?:Command|c)\s+(.+)$',
    re.IGNORECASE | re.DOTALL,
)
_WRITE_COMMAND = re.compile(
    r"(?i)(?:\bset-content\b|\badd-content\b|\bout-file\b|\bremove-item\b|"
    r"\bmove-item\b|\bcopy-item\b|\bnew-item\b|\bdel\b|\berase\b|"
    r"\brm\b|\bmv\b|\bcp\b|\btouch\b|\bmkdir\b|\bgit\s+(?:apply|clean|checkout|"
    r"reset|merge|cherry-pick)\b|(?<![<])>{1,2}(?![>]))"
)


# 只读工具：它们的入参里也有 path / file_path，但访问不产生写入。
# 对这些只校验「有没有跑出 worktree」，不校验可写白名单——
# 否则只读角色（reviewer 的 writablePaths 是空的）连要复核的文件都打不开，
# 一 Read 就被判越界。这正是集成时 reviewer 节点失败的原因。
#
# 名单之外的工具一律按写处理（fail-closed）：不认识的工具宁可误拦，
# 也不能让一个能写的工具因为没在名单里就绕过白名单。
_READ_ONLY_TOOLS = frozenset(
    {
        "read",
        "read_file",
        "readfile",
        "view",
        "cat",
        "glob",
        "grep",
        "search",
        "ls",
        "list_dir",
        "list_directory",
        "notebookread",
        "websearch",
        "webfetch",
        "todowrite",
    }
)


class PathGuard:
    def __init__(self, worktree_path: str, allowed_paths: Iterable[str], *, platform: str | None = None, input_attachments=None) -> None:
        self.root = Path(worktree_path).resolve()
        self.platform = platform or os.name
        self.patterns = tuple(self._normalise_pattern(item) for item in allowed_paths)
        from adapters.attachment_input import checked_inputs
        self.input_files = {os.path.normcase(str(Path(v.local_path).resolve())): v for v in checked_inputs(input_attachments)}

    @staticmethod
    def _normalise_pattern(pattern: str) -> str:
        value = pattern.replace("\\", "/").lstrip("./")
        return value or "__never_match__"

    def _relative(self, candidate: str) -> str | None:
        try:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = self.root / path
            relative = path.resolve(strict=False).relative_to(self.root)
        except (ValueError, OSError, RuntimeError):
            return None
        return relative.as_posix()

    def allows(self, candidate: str) -> bool:
        try:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = self.root / path
            if os.path.normcase(str(path.resolve())) in self.input_files:
                return False
        except (OSError, ValueError, RuntimeError):
            return False
        relative = self._relative(candidate)
        if relative is None:
            return False
        if relative == ".git" or relative.startswith(".git/"):
            return False
        for pattern in self.patterns:
            if pattern.endswith("/**"):
                prefix = pattern[:-3].rstrip("/")
                if relative == prefix or relative.startswith(prefix + "/"):
                    return True
            if fnmatch.fnmatchcase(relative, pattern):
                return True
        return False

    def violations(self, candidates: Iterable[str]) -> list[str]:
        return [item for item in candidates if not self.allows(item)]

    def contains(self, candidate: str) -> bool:
        """路径是否落在 worktree 内。只读工具用这个，不看可写白名单。"""
        try:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = self.root / path
            entry = self.input_files.get(os.path.normcase(str(path.resolve())))
            if entry is None:
                return self._relative(candidate) is not None
            if path.is_symlink():
                return False
            from adapters.attachment_input import checked_inputs
            checked_inputs([entry])
            return True
        except (OSError, ValueError, RuntimeError):
            return False
        except Exception:
            return False

    def inspect_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> list[str]:
        candidates = list(self._extract_paths(tool_input))
        if tool_name.lower() in _READ_ONLY_TOOLS:
            # 读操作只要不跑出 worktree 就放行。跑出去仍然拦——
            # 越界读同样是信息泄漏，不能因为「只是读」就不管。
            return [item for item in candidates if not self.contains(item)]
        violations = self.violations(candidates)
        if violations:
            return violations
        if tool_name.lower() in {"bash", "powershell", "shell", "exec_command"}:
            command = str(tool_input.get("command") or tool_input.get("cmd") or "")
            if self.platform != 'nt':
                return self._posix_command(command)
            command = self._shell_payload(command)
            absolute_paths = self._command_paths(command)
            violations = self.violations(absolute_paths)
            if violations:
                return violations
            if _WRITE_COMMAND.search(command) and not absolute_paths:
                return ["<unresolved shell write target>"]
        return []

    @staticmethod
    def _trusted_program(value: str, names: tuple[str, ...]) -> bool:
        # The actual PATH discovery is authoritative, not just a basename.
        for name in names:
            found = shutil.which(name)
            if found and ((value == name) or Path(value).resolve() == Path(found).resolve()):
                return True
        return False

    @classmethod
    def _posix_payload(cls, command: str) -> str | None:
        for _ in range(4):
            try:
                tokens = shlex.split(command, posix=True)
            except ValueError:
                return None
            if not tokens:
                return command
            if Path(tokens[0]).name == 'env':
                if not cls._trusted_program(tokens.pop(0), ('env',)):
                    return None
                while tokens and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=[^$`]*', tokens[0]):
                    key = tokens.pop(0).split('=', 1)[0]
                    if key in {'PATH','ENV','BASH_ENV','ZDOTDIR','SHELLOPTS','BASHOPTS','CDPATH','LD_PRELOAD','LD_LIBRARY_PATH'} or key.startswith('DYLD_'):
                        return None
                if not tokens:
                    return None
            launcher = tokens[0]
            if Path(launcher).name not in {'bash','sh','zsh'}:
                return command
            if not cls._trusted_program(launcher, ('bash','sh','zsh')):
                return None
            # Unknown shell modes/flags cannot accidentally exempt a launcher.
            if len(tokens) != 3 or tokens[1] != '-c':
                return None
            command = tokens[2]
        return None

    def _posix_command(self, command: str) -> list[str]:
        payload = self._posix_payload(command)
        if payload is None:
            return ['<unresolved shell wrapper>']
        # Shell expansion/cwd changes cannot be proven against this worktree.
        if re.search(r'[$`]|(?:^|[;&|\s])(?:cd|eval|source|exec)\s|(?:^|[;&|\s])\.\s', payload):
            return ['<unresolved shell write target>']
        paths = []
        # Include embedded quoted paths (e.g. node -e writeFileSync('/...')).
        remainder = list(payload)
        for match in re.finditer(r'''(["'])((?:/|~/|\.\./)[^\r\n]*?)\1''', payload):
            paths.append(match.group(2))
            remainder[match.start():match.end()] = ' '*(match.end()-match.start())
        paths.extend(re.findall(r'''(?<![\w:])(?:/|~/|\.\./)[^\s"'|;&<>(),]+''', ''.join(remainder)))
        for match in re.finditer(r'''(?:writeFileSync|appendFileSync|unlinkSync|open)\s*\(\s*(["'])(.*?)\1''', payload):
            paths.append(match.group(2))
        try:
            lexer = shlex.shlex(payload, posix=True, punctuation_chars=';&|<>')
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return ['<unresolved shell write target>']
        writing = False
        start = True
        redirect = None
        for token in tokens:
            if redirect is not None:
                if token in {';', '&&', '||', '|', '&', '>', '>>', '<', '&>', '&>>', '>|', '>&', '<&'}:
                    return ['<unresolved shell write target>']
                # Numeric fd duplication and fd closing do not name a file.
                if not (redirect in {'>&', '<&'} and (token.isdigit() or token == '-')):
                    if any(c in token for c in '*?[]{}'):
                        return ['<unresolved shell write target>']
                    paths.append(token)
                redirect = None
                continue
            if token in {';', '&&', '||', '|', '&'}:
                start, writing = True, False
                continue
            # shlex separates 2>/2>> into the fd token and > / >>.
            if token in {'>', '>>', '<', '&>', '&>>', '>|', '>&', '<&'}:
                redirect = token
                continue
            if re.fullmatch(r'[;&|<>]+', token):
                return ['<unresolved shell write target>']
            if start:
                writing = token in {'rm','mv','cp','touch','mkdir','rmdir','tee','truncate','install','chmod','chown','ln'}
                start = False
            elif writing and not token.startswith('-'):
                if any(c in token for c in '*?[]{}'):
                    return ['<unresolved shell write target>']
                paths.append(token)
        paths = list(dict.fromkeys(paths))
        violations = self.violations(paths)
        if violations:
            return violations
        without_redirects = re.sub(r'[<>]+', '', payload)
        if redirect is not None or ((_WRITE_COMMAND.search(without_redirects) or re.search(r'\b(?:writeFileSync|appendFileSync|unlinkSync)\b',payload)) and not paths):
            return ['<unresolved shell write target>']
        return []

    @staticmethod
    def _shell_payload(command: str) -> str:
        """An installed PowerShell launcher is executable metadata, not a write target.

        Only unwrap the exact launcher found on this Worker's PATH and the known
        -Command form. Unknown executables/flags retain the conservative path check.
        The entire script remains checked, including references to the launcher itself.
        """
        match = _POWERSHELL_LAUNCH.match(command)
        if match is None:
            return command
        launcher = Path(match.group(1)).resolve()
        known = {Path(found).resolve() for name in ('pwsh.exe', 'powershell.exe')
                 if (found := shutil.which(name))}
        return match.group(2) if launcher in known else command

    @staticmethod
    def _command_paths(command: str) -> list[str]:
        # Preserve quoted resource paths containing spaces; don't report C:\Program
        # for a literal C:\Program Files\... argument.
        paths = []
        remainder = list(command)
        for match in _QUOTED_WINDOWS_PATH.finditer(command):
            paths.append(match.group(2))
            remainder[match.start():match.end()] = ' ' * (match.end() - match.start())
        paths.extend(_ABSOLUTE_WINDOWS_PATH.findall(''.join(remainder)))
        return list(dict.fromkeys(paths))

    def validate_changes(self, changes: Iterable[FileChange] | None) -> list[str]:
        if not changes:
            return []
        return self.violations(change.path for change in changes)

    @classmethod
    def _extract_paths(cls, value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = key.lower()
                if lowered in {
                    "path",
                    "file_path",
                    "filepath",
                    "grantroot",
                    "target",
                    "renamedfrom",
                } and isinstance(item, str):
                    yield item
                else:
                    yield from cls._extract_paths(item)
        elif isinstance(value, list):
            for item in value:
                yield from cls._extract_paths(item)
