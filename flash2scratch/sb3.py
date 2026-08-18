from __future__ import annotations

import hashlib
import json
import struct
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__


def uid() -> str:
    return uuid.uuid4().hex[:20]


def png_size(data: bytes) -> tuple[int, int]:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    return 1, 1


TRANSPARENT_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
BLANK_STAGE_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="white"/></svg>'


class BlockBuilder:
    def __init__(self):
        self.blocks: dict[str, dict] = {}

    def add(self, opcode, *, parent=None, next_=None, inputs=None, fields=None, top=False, x=0, y=0, shadow=False, mutation=None):
        block_id = uid()
        block = {
            "opcode": opcode,
            "next": next_,
            "parent": parent,
            "inputs": inputs or {},
            "fields": fields or {},
            "shadow": shadow,
            "topLevel": top,
        }
        if top:
            block.update({"x": x, "y": y})
        if mutation is not None:
            block["mutation"] = mutation
        self.blocks[block_id] = block
        return block_id

    def chain(self, ids):
        for first, second in zip(ids, ids[1:]):
            self.blocks[first]["next"] = second
            self.blocks[second]["parent"] = first
        return ids[0] if ids else None

    @staticmethod
    def num(value):
        return [1, [4, str(value)]]

    @staticmethod
    def text(value):
        return [1, [10, str(value)]]


@dataclass
class Asset:
    data: bytes
    ext: str
    name: str

    @property
    def md5(self):
        return hashlib.md5(self.data).hexdigest()

    @property
    def filename(self):
        return f"{self.md5}.{self.ext}"


@dataclass
class Target:
    name: str
    is_stage: bool
    blocks: BlockBuilder = field(default_factory=BlockBuilder)
    costumes: list[Asset] = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    lists: dict = field(default_factory=dict)
    broadcasts: dict = field(default_factory=dict)
    x: float = 0
    y: float = 0
    size: float = 100
    direction: float = 90
    visible: bool = True


class ScratchProject:
    def __init__(self):
        self.stage = Target("Stage", True)
        self.sprites: dict[str, Target] = {}
        self._assets: dict[str, Asset] = {}

    def sprite(self, name):
        if name not in self.sprites:
            target = Target(name, False)
            target.costumes.append(Asset(TRANSPARENT_SVG, "svg", "proxy"))
            self.sprites[name] = target
        return self.sprites[name]

    def global_var(self, name, value=0):
        for var_id, pair in self.stage.variables.items():
            if pair[0] == name:
                return var_id
        var_id = uid()
        self.stage.variables[var_id] = [name, value]
        return var_id

    def global_list(self, name, items=None):
        for list_id, pair in self.stage.lists.items():
            if pair[0] == name:
                return list_id
        list_id = uid()
        self.stage.lists[list_id] = [name, list(items or [])]
        return list_id

    def broadcast(self, name):
        for broadcast_id, existing in self.stage.broadcasts.items():
            if existing == name:
                return broadcast_id
        broadcast_id = uid()
        self.stage.broadcasts[broadcast_id] = name
        return broadcast_id

    def add_stage_costume(self, path: Path, name=None):
        self.stage.costumes.append(Asset(path.read_bytes(), path.suffix.lower().lstrip("."), name or path.stem))

    def _costume(self, asset):
        self._assets[asset.filename] = asset
        if asset.ext == "png":
            width, height = png_size(asset.data)
            return {
                "assetId": asset.md5,
                "name": asset.name,
                "bitmapResolution": 1,
                "md5ext": asset.filename,
                "dataFormat": "png",
                "rotationCenterX": width / 2,
                "rotationCenterY": height / 2,
            }
        return {
            "assetId": asset.md5,
            "name": asset.name,
            "md5ext": asset.filename,
            "dataFormat": asset.ext,
            "rotationCenterX": 0.5,
            "rotationCenterY": 0.5,
        }

    def _target(self, target, layer):
        if not target.costumes:
            target.costumes.append(Asset(BLANK_STAGE_SVG if target.is_stage else TRANSPARENT_SVG, "svg", "backdrop1" if target.is_stage else "proxy"))
        data = {
            "isStage": target.is_stage,
            "name": target.name,
            "variables": target.variables if target.is_stage else {},
            "lists": target.lists if target.is_stage else {},
            "broadcasts": target.broadcasts if target.is_stage else {},
            "blocks": target.blocks.blocks,
            "comments": {},
            "currentCostume": 0,
            "costumes": [self._costume(asset) for asset in target.costumes],
            "sounds": [],
            "volume": 100,
            "layerOrder": layer,
        }
        if target.is_stage:
            data.update({"tempo": 60, "videoTransparency": 50, "videoState": "off", "textToSpeechLanguage": None})
        else:
            data.update({"visible": target.visible, "x": target.x, "y": target.y, "size": target.size, "direction": target.direction, "draggable": False, "rotationStyle": "all around"})
        return data

    def to_json(self):
        self._assets = {}
        targets = [self._target(self.stage, 0)] + [self._target(target, index + 1) for index, target in enumerate(self.sprites.values())]
        return {
            "targets": targets,
            "monitors": [],
            "extensions": [],
            "meta": {"semver": "3.0.0", "vm": __version__, "agent": f"Flash2Scratch/{__version__}"},
        }

    def save(self, path: Path):
        project = self.to_json()
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(project, separators=(",", ":")))
            for filename, asset in self._assets.items():
                archive.writestr(filename, asset.data)
