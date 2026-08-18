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
    actionscript: str = "Unknown"
    swf_version: int | None = None
    timeline_frames_exported: int = 0
    timeline_unique_frames: int = 0
    duplicate_frames_removed: int = 0
    sampled_frames_removed: int = 0
    estimated_backdrop_memory_mb: float = 0.0
    output_size_mb: float = 0.0

    @property
    def ok(self) -> bool:
        return not any(x.startswith("FATAL:") for x in self.warnings)

    def text(self) -> str:
        lines = [
            "Flash2Scratch conversion report",
            f"Input: {self.swf}",
            f"Output: {self.output}",
            f"SWF version: {self.swf_version if self.swf_version is not None else 'unknown'}",
            f"Runtime: {self.actionscript}",
            f"Script files: {self.source_files}",
            f"Timeline frames rendered by FFDec: {self.timeline_frames_exported}",
            f"Unique rendered frames: {self.timeline_unique_frames}",
            f"Scratch backdrops kept: {self.frame_assets}",
            f"Exact duplicate frames removed: {self.duplicate_frames_removed}",
            f"Unique frames sampled out: {self.sampled_frames_removed}",
            f"Estimated decoded backdrop memory: {self.estimated_backdrop_memory_mb:.1f} MB",
            f"Sprite assets: {self.sprite_assets}",
            f"Output SB3 size: {self.output_size_mb:.1f} MB",
            f"Translated constructs: {len(self.translated)}",
            f"Unsupported constructs: {len(self.unsupported)}",
        ]
        if self.translated:
            lines += ["", "Translated:"] + [f"  + {x}" for x in self.translated]
        if self.unsupported:
            lines += ["", "Unsupported / approximated:"] + [
                f"  - {x}" for x in self.unsupported
            ]
        if self.warnings:
            lines += ["", "Warnings:"] + [f"  ! {x}" for x in self.warnings]
        return "\n".join(lines) + "\n"
