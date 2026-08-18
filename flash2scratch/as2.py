from __future__ import annotations

import re
from pathlib import Path

from .as3 import AS3Program, COMMENT_RE, FrameScript, Handler, Listener, _brace_body


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
    r"\s*=\s*function\s*\((?P<params>[^)]*)\)\s*\{",
    re.M,
)
CLIP_EVENT_RE = re.compile(
    r"\bonClipEvent\s*\(\s*(?P<event>enterFrame|mouseDown|mouseUp|keyDown|load)\s*\)\s*\{",
    re.I | re.M,
)
BUTTON_EVENT_RE = re.compile(
    r"\bon\s*\(\s*(?P<event>release|press|rollOver|rollOut)\s*\)\s*\{",
    re.I | re.M,
)
FUNC_RE = re.compile(
    r"\bfunction\s+(?P<name>[A-Za-z_$][\w$]*)\s*\((?P<params>[^)]*)\)\s*\{",
    re.M,
)
VAR_RE = re.compile(r"\bvar\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?:=\s*(?P<value>[^;]+))?;")


def _owner(raw: str | None) -> str:
    if not raw or raw in {"this", "_root"}:
        return "stage"
    raw = raw.removeprefix("_root.")
    return raw.split(".")[0] or "stage"


def _source_owner_hint(source: Path, root: Path) -> str | None:
    """Use FFDec's script path when it clearly identifies a clip/button owner."""
    try:
        parts = source.relative_to(root).parts[:-1]
    except ValueError:
        parts = source.parts[:-1]
    for raw in reversed(parts):
        part = Path(raw).stem.strip()
        lower = part.lower()
        match = re.fullmatch(
            r"(?:sprite|movieclip|clip|character|button)[_. -]*(\d+)",
            part,
            re.I,
        )
        if match:
            return f"symbol_{int(match.group(1))}"
        if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
            if lower in {"scripts", "script", "actions", "action", "frames", "frame"}:
                continue
            if lower.startswith(("frame", "doaction", "doinitaction")):
                continue
            return part
    return None


def _param_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        raw = raw.split("=", 1)[0].strip()
        if ":" in raw:
            raw = raw.split(":", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_$][\w$]*", raw):
            names.append(raw)
    return names


def _add_handler(p, prefix, owner, event, body, index, params=None, source=None):
    name = f"__as2_{prefix}_{index}"
    p.handlers[name] = Handler(name, body, params or [])
    p.listeners.append(Listener(owner, event, name, source))
    if owner != "stage":
        p.display_objects.add(owner)


def _block_span(text: str, start: int) -> tuple[int, str, int]:
    open_brace = text.find("{", start)
    if open_brace < 0:
        return start, "", start
    body, end = _brace_body(text, open_brace)
    while end < len(text) and text[end].isspace():
        end += 1
    if end < len(text) and text[end] == ";":
        end += 1
    return start, body, end


def _mask_spans(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(max(0, start), min(len(chars), end)):
            chars[index] = "\n" if chars[index] == "\n" else " "
    return "".join(chars)


def _frame_from_path(path: Path, root: Path) -> int | None:
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        relative = str(path)
    for pattern in (
        r"(?i)\bframe[\s_.-]*(\d+)\b",
        r"(?i)\bdoaction[\s_.\[\]-]*(\d+)\b",
    ):
        match = re.search(pattern, relative)
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def _has_executable_code(text: str) -> bool:
    cleaned = re.sub(r"(?m)^\s*#(?:initclip|endinitclip).*$", "", text)
    cleaned = re.sub(r"\b(?:var|const)\s+[A-Za-z_$][\w$]*\s*;", "", cleaned)
    cleaned = re.sub(r"[;\s{}]+", "", cleaned)
    return bool(cleaned)


def parse_sources(root: Path) -> AS3Program:
    files = sorted(root.rglob("*.as")) if root.exists() else []
    p = AS3Program(sources=files)
    all_text: list[str] = []
    synthetic_index = 0
    clip_map = {
        "enterframe": "Event.ENTER_FRAME",
        "mousedown": "MouseEvent.CLICK",
        "mouseup": "MouseEvent.CLICK",
        "keydown": "KeyboardEvent.KEY_DOWN",
        "load": "Event.GREEN_FLAG",
    }
    button_map = {
        "release": "MouseEvent.CLICK",
        "press": "MouseEvent.CLICK",
        "rollover": "MouseEvent.MOUSE_OVER",
        "rollout": "MouseEvent.MOUSE_OUT",
    }

    for source in files:
        raw = source.read_text(encoding="utf-8", errors="replace")
        text = COMMENT_RE.sub("", raw)
        all_text.append(text)
        spans: list[tuple[int, int]] = []

        for match in FUNC_RE.finditer(text):
            start, body, end = _block_span(text, match.start())
            if end <= start:
                continue
            p.handlers[match.group("name")] = Handler(
                match.group("name"), body, _param_names(match.group("params") or "")
            )
            spans.append((start, end))

        for match in ASSIGNED_EVENT_RE.finditer(text):
            start, body, end = _block_span(text, match.start())
            if end <= start:
                continue
            synthetic_index += 1
            _add_handler(
                p,
                "event",
                _owner(match.group("owner")),
                EVENT_MAP[match.group("event")],
                body,
                synthetic_index,
                _param_names(match.group("params") or ""),
                source,
            )
            spans.append((start, end))

        source_owner = _source_owner_hint(source, root) or "stage"
        for match in CLIP_EVENT_RE.finditer(text):
            start, body, end = _block_span(text, match.start())
            if end <= start:
                continue
            synthetic_index += 1
            _add_handler(
                p,
                "clip",
                source_owner,
                clip_map[match.group("event").lower()],
                body,
                synthetic_index,
                source=source,
            )
            spans.append((start, end))

        for match in BUTTON_EVENT_RE.finditer(text):
            start, body, end = _block_span(text, match.start())
            if end <= start:
                continue
            synthetic_index += 1
            _add_handler(
                p,
                "button",
                source_owner,
                button_map[match.group("event").lower()],
                body,
                synthetic_index,
                source=source,
            )
            spans.append((start, end))

        remainder = _mask_spans(text, spans)
        remainder = re.sub(r"(?m)^\s*#(?:initclip|endinitclip).*$", "", remainder)
        if _has_executable_code(remainder):
            p.frame_scripts.append(FrameScript(remainder, _frame_from_path(source, root), source))

    text = "\n".join(all_text)
    p.text = text
    for match in VAR_RE.finditer(text):
        value = match.group("value")
        if value is not None:
            p.variables.setdefault(match.group("name"), value.strip())
    for name in re.findall(
        r"\b(?:_root\.)?([A-Za-z_$][\w$]*)\s*\.\s*(?:_x|_y|_rotation|_visible|_alpha|_xscale|_yscale|_currentframe|_totalframes)\b",
        text,
    ):
        if name not in {"this", "_root"}:
            p.display_objects.add(name)
    for name in re.findall(
        r"\b(?:_root\.)?([A-Za-z_$][\w$]*)\s*\.\s*(?:gotoAndStop|gotoAndPlay|play|stop|hitTest|swapDepths|startDrag|removeMovieClip)\s*\(",
        text,
    ):
        if name not in {"this", "_root"}:
            p.display_objects.add(name)
    return p
