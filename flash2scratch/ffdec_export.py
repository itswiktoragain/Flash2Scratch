from __future__ import annotations

import shutil
from pathlib import Path

from .ffdec import FFDecResult, _run


def export_core_swf(ffdec: str, swf: Path, root: Path) -> FFDecResult:
    """Export scripts/symbol assets/XML without rendering every main-timeline frame."""
    root.mkdir(parents=True, exist_ok=True)
    _run(
        ffdec,
        [
            "-format",
            "script:as,sprite:png,button:png,sound:mp3_wav",
            "-export",
            "script,sprite,button,sound,symbolClass",
            str(root),
            str(swf),
        ],
    )
    xml = root / "movie.xml"
    _run(ffdec, ["-swf2xml", str(swf), str(xml)])
    return FFDecResult(
        root,
        root / "scripts",
        root / "frames",
        root / "sprites",
        root / "sounds",
        xml,
    )


def export_selected_frames(
    ffdec: str,
    swf: Path,
    result: FFDecResult,
    frame_numbers: list[int] | None,
) -> None:
    """Render only selected main-timeline frames using FFDec's -select option."""
    if result.frames.exists():
        shutil.rmtree(result.frames)

    args = ["-format", "frame:png"]
    if frame_numbers:
        selection = "0:" + ",".join(str(frame) for frame in sorted(set(frame_numbers)))
        args += ["-select", selection]
    args += ["-export", "frame", str(result.root), str(swf)]
    _run(ffdec, args)
