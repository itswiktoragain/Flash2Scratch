from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Placement:
    character_id: int
    name: str | None = None
    owner_character_id: int | None = None
    depth: int | None = None

    @property
    def top_level(self) -> bool:
        return self.owner_character_id is None


@dataclass
class SWFInfo:
    width: int = 480
    height: int = 360
    frame_rate: float = 30.0
    instances: dict[str, int] = field(default_factory=dict)
    placements: list[Placement] = field(default_factory=list)
    sprite_ids: set[int] = field(default_factory=set)
    button_ids: set[int] = field(default_factory=set)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr(element: ET.Element, name: str) -> str | None:
    wanted = name.lower()
    for key, value in element.attrib.items():
        if _local_name(key).lower() == wanted:
            return value
    return None


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+", str(value))
        return int(match.group(0)) if match else None


def _kind(element: ET.Element) -> str:
    # FFDec XML versions have used both named tag elements and generic item
    # elements with a type/class attribute. Search both forms.
    pieces = [_local_name(element.tag)]
    for key in ("type", "class", "tagType", "name"):
        value = _attr(element, key)
        if value:
            pieces.append(value)
    return " ".join(pieces).lower()


def _parse_with_elementtree(text: str, info: SWFInfo) -> bool:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return False

    frame_rate = _attr(root, "frameRate") or _attr(root, "framerate")
    if frame_rate:
        try:
            info.frame_rate = float(frame_rate)
        except ValueError:
            pass

    # First pass: learn which character IDs are real timeline symbols/buttons.
    for element in root.iter():
        kind = _kind(element)
        character_id = _integer(_attr(element, "characterId"))
        if character_id is None:
            character_id = _integer(_attr(element, "characterID"))
        if character_id is None:
            continue
        if "definesprite" in kind:
            info.sprite_ids.add(character_id)
        elif "definebutton" in kind:
            info.button_ids.add(character_id)

    def walk(element: ET.Element, owner: int | None = None) -> None:
        kind = _kind(element)
        character_id = _integer(_attr(element, "characterId"))
        if character_id is None:
            character_id = _integer(_attr(element, "characterID"))

        current_owner = owner
        if "definesprite" in kind and character_id is not None:
            current_owner = character_id

        if "placeobject" in kind and character_id is not None:
            raw_name = _attr(element, "name")
            name = raw_name.strip() if raw_name and raw_name.strip() else None
            depth = _integer(_attr(element, "depth"))
            placement = Placement(character_id, name, owner, depth)
            info.placements.append(placement)
            if name:
                info.instances.setdefault(name, character_id)

        for child in list(element):
            walk(child, current_owner)

    walk(root)
    return True


def _regex_fallback(text: str, info: SWFInfo) -> None:
    match = re.search(r'\bframeRate="([0-9.+-]+)"', text, re.I)
    if match:
        try:
            info.frame_rate = float(match.group(1))
        except ValueError:
            pass

    for tag in re.findall(r"<[^>]+>", text):
        lower = tag.lower()
        cid_match = re.search(r'\bcharacterid="(\d+)"', tag, re.I)
        cid = int(cid_match.group(1)) if cid_match else None
        if cid is not None and "definesprite" in lower:
            info.sprite_ids.add(cid)
        if cid is not None and "definebutton" in lower:
            info.button_ids.add(cid)
        if cid is None or "placeobject" not in lower:
            continue
        name_match = re.search(r'\bname="([^"]+)"', tag, re.I)
        name = name_match.group(1) if name_match else None
        depth_match = re.search(r'\bdepth="(\d+)"', tag, re.I)
        depth = int(depth_match.group(1)) if depth_match else None
        info.placements.append(Placement(cid, name, None, depth))
        if name:
            info.instances.setdefault(name, cid)


def parse_swf_xml(path: Path) -> SWFInfo:
    info = SWFInfo()
    if not path.exists():
        return info
    text = path.read_text(encoding="utf-8", errors="replace")
    if not _parse_with_elementtree(text, info):
        _regex_fallback(text, info)
    return info
