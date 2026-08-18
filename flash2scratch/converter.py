from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .as2 import parse_sources as parse_as2_sources
from .as3 import parse_sources as parse_as3_sources
from .compiler import AS3Compiler
from .ffdec import detect_runtime, export_swf, find_ffdec
from .frames import compact_frames
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
        result = export_swf(exe, swf, root)
        _compile(result, output, report, runtime.vm)
    else:
        with tempfile.TemporaryDirectory(prefix="flash2scratch-") as temp_dir:
            result = export_swf(exe, swf, Path(temp_dir))
            _compile(result, output, report, runtime.vm)

    return report


def _compile(result, output, report, vm):
    info = parse_swf_xml(result.xml)

    if vm == "avm1":
        program = parse_as2_sources(result.scripts)
    elif vm == "avm2":
        program = parse_as3_sources(result.scripts)
    else:
        program = parse_as3_sources(result.scripts)

    report.source_files = len(program.sources)
    project = ScratchProject()

    frames = _pngs(result.frames)
    plan = compact_frames(frames, program.text)
    report.timeline_frames_exported = plan.original_count
    report.timeline_unique_frames = plan.unique_count
    report.frame_assets = plan.kept_count
    report.duplicate_frames_removed = plan.duplicates_removed
    report.sampled_frames_removed = plan.sampled_out
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
            f"{plan.original_count} rendered frames -> {plan.kept_count} Scratch backdrops"
        )
        if plan.sampled_out:
            report.warnings.append(
                f"Long timeline sampled for Scratch safety: {plan.sampled_out} unique "
                "rendered frames were omitted and mapped to nearby retained backdrops."
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
