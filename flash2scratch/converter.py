from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .as2 import parse_sources as parse_as2_sources
from .as3 import parse_sources as parse_as3_sources
from .compiler import AS3Compiler
from .ffdec import detect_runtime, find_ffdec
from .ffdec_export import export_core_swf, export_selected_frames
from .frames import choose_frame_numbers, compact_frames
from .report import ConversionReport
from .sb3 import Asset, ScratchProject
from .swfxml import parse_swf_xml


def _natural(path):
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", str(path))
    ]


def _pngs(root):
    return sorted(root.rglob("*.png"), key=_natural) if root.exists() else []


def _sprite(root, cid):
    if not root.exists():
        return None
    hits = [
        path
        for path in root.rglob("*.png")
        if re.search(rf"(^|\D){cid}(\D|$)", path.stem)
    ]
    return sorted(hits, key=lambda path: (len(str(path)), str(path)))[0] if hits else None


def _frame_count_from_xml(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in (
        r'\bframeCount\s*=\s*"(\d+)"',
        r'\bframecount\s*=\s*"(\d+)"',
    ):
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
    return 0


def _exported_frame_numbers(
    frames: list[Path], requested: list[int] | None
) -> list[int]:
    """Recover original frame numbers from FFDec filenames when possible."""
    if not frames:
        return []
    requested_set = set(requested or [])
    parsed: list[int] = []
    for path in frames:
        numbers = re.findall(r"\d+", path.stem)
        if not numbers:
            parsed = []
            break
        parsed.append(int(numbers[-1]))

    if parsed and len(set(parsed)) == len(parsed):
        if not requested_set or all(number in requested_set for number in parsed):
            return parsed

    if requested and len(requested) == len(frames):
        return list(requested)
    return list(range(1, len(frames) + 1))


def convert(swf, output, *, ffdec=None, keep_temp=None):
    swf = Path(swf).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not swf.is_file():
        raise FileNotFoundError(swf)

    exe = find_ffdec(ffdec)
    report = ConversionReport(swf, output)
    runtime = detect_runtime(exe, swf)
    report.actionscript = runtime.actionscript
    report.swf_version = runtime.swf_version

    if runtime.vm == "avm1":
        report.translated.append(
            f"Detected SWF v{runtime.swf_version}: ActionScript 1/2 / AVM1"
        )
    elif runtime.vm == "avm2":
        report.translated.append(
            f"Detected SWF v{runtime.swf_version}: ActionScript 3 / AVM2"
        )
    else:
        report.warnings.append(
            f"SWF v{runtime.swf_version} contains no ActionScript bytecode FFDec "
            "could identify; timeline/assets will still be converted."
        )

    if keep_temp:
        root = Path(keep_temp).expanduser().resolve()
        result = export_core_swf(exe, swf, root)
        _compile(exe, swf, result, output, report, runtime.vm)
    else:
        with tempfile.TemporaryDirectory(prefix="flash2scratch-") as temp_dir:
            result = export_core_swf(exe, swf, Path(temp_dir))
            _compile(exe, swf, result, output, report, runtime.vm)

    return report


def _compile(exe, swf, result, output, report, vm):
    info = parse_swf_xml(result.xml)

    if vm == "avm1":
        program = parse_as2_sources(result.scripts)
    elif vm == "avm2":
        program = parse_as3_sources(result.scripts)
    else:
        program = parse_as3_sources(result.scripts)

    report.source_files = len(program.sources)
    project = ScratchProject()

    total_frames = _frame_count_from_xml(result.xml)
    requested_frames = (
        choose_frame_numbers(total_frames, program.text)
        if total_frames > 0
        else None
    )
    export_selected_frames(exe, swf, result, requested_frames)

    frames = _pngs(result.frames)
    rendered_numbers = _exported_frame_numbers(frames, requested_frames)
    if total_frames <= 0:
        total_frames = max(rendered_numbers, default=len(frames))

    plan = compact_frames(
        frames,
        program.text,
        frame_numbers=rendered_numbers,
        total_frames=total_frames,
    )
    report.timeline_frames_exported = plan.original_count
    report.timeline_frames_rendered = plan.rendered_count
    report.timeline_unique_frames = plan.unique_count
    report.frame_assets = plan.kept_count
    report.duplicate_frames_removed = plan.duplicates_removed
    report.sampled_frames_removed = max(
        0,
        plan.original_count - plan.kept_count - plan.duplicates_removed,
    )
    report.estimated_backdrop_memory_mb = plan.estimated_decoded_bytes / (1024 * 1024)

    for selected in plan.selected:
        project.add_stage_costume(selected.path, f"frame {selected.original_index}")

    if not frames:
        report.warnings.append(
            "FFDec exported no main-timeline frame PNGs; using a blank stage."
        )
    elif plan.kept_count < plan.original_count:
        report.translated.append(
            "Timeline compacted: "
            f"{plan.original_count} Flash frames -> {plan.kept_count} Scratch backdrops"
        )
        report.warnings.append(
            "Long timeline compacted for Scratch/Chrome safety; omitted frames map "
            "to nearby retained backdrops."
        )

    for name in sorted(program.display_objects):
        sprite = project.sprite(name)
        cid = info.instances.get(name)
        asset = _sprite(result.sprites, cid) if cid is not None else None
        if asset:
            sprite.costumes = [Asset(asset.read_bytes(), "png", name)]
            report.sprite_assets += 1

    AS3Compiler(
        project,
        program,
        report,
        info.frame_rate,
        frame_map=plan.frame_map,
    ).compile()
    project.save(output)
    try:
        report.output_size_mb = output.stat().st_size / (1024 * 1024)
    except OSError:
        pass
    output.with_suffix(output.suffix + ".report.txt").write_text(
        report.text(), encoding="utf-8"
    )
