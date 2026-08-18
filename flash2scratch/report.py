from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionReport:
    swf: Path
    output: Path
    warnings: list[str] = field(default_factory=list)
    translated: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    source_files: int = 0
    frame_assets: int = 0
    sprite_assets: int = 0

    @property
    def ok(self) -> bool:
        return not any(x.startswith("FATAL:") for x in self.warnings)

    def text(self) -> str:
        lines = [
            "Flash2Scratch conversion report",
            f"Input: {self.swf}",
            f"Output: {self.output}",
            f"AS3 files: {self.source_files}",
            f"Timeline frames: {self.frame_assets}",
            f"Sprite assets: {self.sprite_assets}",
            f"Translated constructs: {len(self.translated)}",
            f"Unsupported constructs: {len(self.unsupported)}",
        ]
        if self.translated:
            lines += ["", "Translated:"] + [f"  + {x}" for x in self.translated]
        if self.unsupported:
            lines += ["", "Unsupported / approximated:"] + [f"  - {x}" for x in self.unsupported]
        if self.warnings:
            lines += ["", "Warnings:"] + [f"  ! {x}" for x in self.warnings]
        return "\n".join(lines) + "\n"
