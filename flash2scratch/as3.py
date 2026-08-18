from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Handler:
    name: str
    body: str
    params: list[str] = field(default_factory=list)
    owner: str = "stage"
    source: Path | None = None


@dataclass
class Listener:
    owner: str
    event: str
    handler: str
    source: Path | None = None


@dataclass
class FrameScript:
    body: str
    frame: int | None = None
    source: Path | None = None


@dataclass
class AS3Program:
    sources: list[Path] = field(default_factory=list)
    text: str = ""
    handlers: dict[str, Handler] = field(default_factory=dict)
    listeners: list[Listener] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    display_objects: set[str] = field(default_factory=set)
    frame_scripts: list[FrameScript] = field(default_factory=list)


COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
FUNC_RE = re.compile(
    r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\((?P<params>[^)]*)\)"
    r"\s*(?::\s*[\w.$<>]+)?\s*\{",
    re.M,
)
LISTENER_RE = re.compile(
    r"(?P<owner>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*|this|stage)"
    r"\s*\.\s*addEventListener\s*\(\s*"
    r"(?P<event>[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*)\s*,\s*"
    r"(?P<handler>[A-Za-z_$][\w$]*)",
    re.M,
)
VAR_RE = re.compile(
    r"\bvar\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"\s*(?::\s*(?P<type>[\w.$<>]+))?"
    r"\s*(?:=\s*(?P<value>[^;]+))?;"
)


def _brace_body(text: str, open_brace: int) -> tuple[str, int]:
    depth = 0
    quote = None
    esc = False
    for i in range(open_brace, len(text)):
        ch = text[i]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1 : i], i + 1
    return text[open_brace + 1 :], len(text)


def _param_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        raw = raw.split("=", 1)[0].strip()
        name = raw.split(":", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
            names.append(name)
    return names


def parse_sources(root: Path) -> AS3Program:
    files = sorted(root.rglob("*.as")) if root.exists() else []
    p = AS3Program(sources=files)
    text = COMMENT_RE.sub(
        "",
        "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files),
    )
    p.text = text

    for match in FUNC_RE.finditer(text):
        open_brace = text.find("{", match.start())
        body, _ = _brace_body(text, open_brace)
        p.handlers[match.group(1)] = Handler(
            match.group(1), body, _param_names(match.group("params") or "")
        )

    for match in LISTENER_RE.finditer(text):
        owner = "stage" if match.group("owner") == "this" else match.group("owner")
        p.listeners.append(Listener(owner, match.group("event"), match.group("handler")))
        if owner != "stage":
            p.display_objects.add(owner.split(".")[0])

    for match in VAR_RE.finditer(text):
        name = match.group("name")
        typ = match.group("type") or ""
        value = match.group("value")
        if re.search(r"(MovieClip|Sprite|SimpleButton|DisplayObject|Bitmap|TextField)$", typ):
            p.display_objects.add(name)
        elif value is not None:
            p.variables[name] = value.strip()

    for name in re.findall(
        r"\b([A-Za-z_$][\w$]*)\s*\.\s*(?:x|y|rotation|visible|alpha|scaleX|scaleY)\b",
        text,
    ):
        if name not in {"this", "stage"}:
            p.display_objects.add(name)
    return p


def split_statements(body: str) -> list[str]:
    out: list[str] = []
    start = 0
    depth = 0
    quote = None
    esc = False
    for i, ch in enumerate(body):
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            statement = body[start:i].strip()
            if statement:
                out.append(statement)
            start = i + 1
    tail = body[start:].strip()
    if tail:
        out.append(tail)
    return out
