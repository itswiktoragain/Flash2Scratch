from __future__ import annotations

import re
from pathlib import Path

from .as3 import AS3Program, Handler, Listener, COMMENT_RE, _brace_body


EVENT_MAP = {
    "onEnterFrame": "Event.ENTER_FRAME",
    "onRelease": "MouseEvent.CLICK",
    "onPress": "MouseEvent.CLICK",
    "onMouseDown": "MouseEvent.CLICK",
    "onKeyDown": "KeyboardEvent.KEY_DOWN",
}

ASSIGNED_EVENT_RE = re.compile(
    r"(?:(?P<owner>(?:_root\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\.\s*)?"
    r"(?P<event>onEnterFrame|onRelease|onPress|onMouseDown|onKeyDown)"
    r"\s*=\s*function\s*\([^)]*\)\s*\{",
    re.M,
)
CLIP_EVENT_RE = re.compile(
    r"\bonClipEvent\s*\(\s*(?P<event>enterFrame|mouseDown|mouseUp|keyDown)\s*\)\s*\{",
    re.I | re.M,
)
BUTTON_EVENT_RE = re.compile(
    r"\bon\s*\(\s*(?P<event>release|press)\s*\)\s*\{",
    re.I | re.M,
)
FUNC_RE = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M)
VAR_RE = re.compile(
    r"\bvar\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?:=\s*(?P<value>[^;]+))?;"
)


def _owner(raw: str | None) -> str:
    if not raw or raw in {"this", "_root"}:
        return "stage"
    raw = raw.removeprefix("_root.")
    return raw.split(".")[0] or "stage"


def _add_handler(p: AS3Program, prefix: str, owner: str, event: str, body: str, index: int) -> None:
    name = f"__as2_{prefix}_{index}"
    p.handlers[name] = Handler(name, body)
    p.listeners.append(Listener(owner, event, name))
    if owner != "stage":
        p.display_objects.add(owner)


def parse_sources(root: Path) -> AS3Program:
    files = sorted(root.rglob("*.as")) if root.exists() else []
    p = AS3Program(sources=files)
    text = COMMENT_RE.sub(
        "",
        "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files),
    )
    p.text = text

    for match in FUNC_RE.finditer(text):
        body, _ = _brace_body(text, text.find("{", match.start()))
        p.handlers.setdefault(match.group(1), Handler(match.group(1), body))

    # Classic timeline/movie-clip style:
    # player.onEnterFrame = function() { ... };
    for index, match in enumerate(ASSIGNED_EVENT_RE.finditer(text), 1):
        body, _ = _brace_body(text, text.find("{", match.start()))
        owner = _owner(match.group("owner"))
        event = EVENT_MAP[match.group("event")]
        _add_handler(p, "event", owner, event, body, index)

    clip_map = {
        "enterframe": "Event.ENTER_FRAME",
        "mousedown": "MouseEvent.CLICK",
        "mouseup": "MouseEvent.CLICK",
        "keydown": "KeyboardEvent.KEY_DOWN",
    }
    for index, match in enumerate(CLIP_EVENT_RE.finditer(text), 1):
        body, _ = _brace_body(text, text.find("{", match.start()))
        _add_handler(p, "clip", "stage", clip_map[match.group("event").lower()], body, index)

    button_map = {"release": "MouseEvent.CLICK", "press": "MouseEvent.CLICK"}
    for index, match in enumerate(BUTTON_EVENT_RE.finditer(text), 1):
        body, _ = _brace_body(text, text.find("{", match.start()))
        _add_handler(p, "button", "stage", button_map[match.group("event").lower()], body, index)

    for match in VAR_RE.finditer(text):
        value = match.group("value")
        if value is not None:
            p.variables[match.group("name")] = value.strip()

    for name in re.findall(
        r"\b(?:_root\.)?([A-Za-z_$][\w$]*)\s*\.\s*"
        r"(?:_x|_y|_rotation|_visible|_alpha|_xscale|_yscale)\b",
        text,
    ):
        if name not in {"this", "_root"}:
            p.display_objects.add(name)

    return p
