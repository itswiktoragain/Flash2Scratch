from __future__ import annotations

import hashlib
import re
from pathlib import Path


DEFAULT_MAX_SYMBOL_COSTUMES = 48


def _natural(path: Path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def _token_matches(value: str, character_id: int) -> bool:
    return re.search(rf"(^|\D){int(character_id)}(\D|$)", value) is not None


def _evenly_spaced(paths: list[Path], count: int) -> list[Path]:
    if count <= 0 or not paths:
        return []
    if len(paths) <= count:
        return list(paths)
    if count == 1:
        return [paths[0]]
    result: list[Path] = []
    last = len(paths) - 1
    for slot in range(count):
        index = round(slot * last / (count - 1))
        path = paths[index]
        if path not in result:
            result.append(path)
    if len(result) < count:
        for path in paths:
            if path not in result:
                result.append(path)
                if len(result) == count:
                    break
    return result


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[bytes] = set()
    result: list[Path] = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).digest()
        if digest in seen:
            continue
        seen.add(digest)
        result.append(path)
    return result


def _matching_directories(root: Path, character_id: int) -> list[Path]:
    """Find FFDec sprite directories which identify a character ID.

    FFDec frequently exports sprite frames as e.g. sprites/123/1.png. Looking
    only at PNG stems is unsafe because every sprite can contain a 1.png.
    """
    if not root.exists():
        return []
    candidates: list[Path] = []
    for directory in (path for path in root.rglob("*") if path.is_dir()):
        relative = directory.relative_to(root)
        if any(_token_matches(part, character_id) for part in relative.parts):
            if any(directory.rglob("*.png")):
                candidates.append(directory)
    candidates.sort(key=lambda path: (len(path.relative_to(root).parts), len(str(path)), str(path).lower()))
    return candidates


def symbol_frames(
    root: Path,
    character_id: int,
    *,
    max_costumes: int = DEFAULT_MAX_SYMBOL_COSTUMES,
) -> list[Path]:
    """Return the actual exported PNG sequence for one Flash character.

    Directory identity is preferred. Filename matching is only a strict
    fallback for FFDec layouts which put a character preview directly in the
    sprite export root.
    """
    directories = _matching_directories(root, character_id)
    if directories:
        paths = sorted(directories[0].rglob("*.png"), key=_natural)
    else:
        paths = []
        if root.exists():
            cid = str(int(character_id))
            strict = re.compile(rf"^{re.escape(cid)}(?:$|[_ .-])")
            paths = sorted(
                [path for path in root.rglob("*.png") if strict.search(path.stem)],
                key=_natural,
            )

    paths = _dedupe(paths)
    return _evenly_spaced(paths, max(1, int(max_costumes)))
