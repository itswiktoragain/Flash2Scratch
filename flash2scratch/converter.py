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
from .symbols import symbol_frames


MAX_RECONSTRUCTED_SYMBOLS = 120


def _natural(path):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(path))]


def _pngs(root):
    return sorted(root.rglob("*.png"), key=_natural) if root.exists() else []


def _frame_count_from_xml(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for pattern in (r'\bframeCount\s*=\s*"(\d+)"', r'\bframecount\s*=\s*"(\d+)"'):
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
    return 0


def _exported_frame_numbers(frames: list[Path], requested: list[int] | None) -> list[int]:
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


def _unique_name(base: str, used: set[str]) -> str:
    base = base.strip() or "symbol"
    if base not in used:
        used.add(base)
        return base
    suffix = 2
    while f"{base}_{suffix}" in used:
        suffix += 1
    name = f"{base}_{suffix}"
    used.add(name)
    return name


def _symbol_candidates(info, program):
    candidates: list[tuple[str, int | None, bool]] = []
    seen_named: set[str] = set()
    for name in sorted(program.display_objects):
        candidates.append((name, info.instances.get(name), True))
        seen_named.add(name)
    for placement in info.placements:
        if placement.name and placement.name not in seen_named:
            candidates.append((placement.name, placement.character_id, False))
            seen_named.add(placement.name)
    anonymous_counts: dict[int, int] = {}
    for placement in info.placements:
        if not placement.top_level or placement.name:
            continue
        cid = placement.character_id
        if info.sprite_ids or info.button_ids:
            if cid not in info.sprite_ids and cid not in info.button_ids:
                continue
        anonymous_counts[cid] = anonymous_counts.get(cid, 0) + 1
        number = anonymous_counts[cid]
        base = f"symbol_{cid}" if number == 1 else f"symbol_{cid}_{number}"
        candidates.append((base, cid, False))
    return candidates


def _install_symbol_animation(project: ScratchProject, sprite, name: str, fps: float) -> None:
    if len(sprite.costumes) <= 1:
        return
    play_var = f"__f2s_symbol_play_{name}"
    play_id = project.global_var(play_var, 1)
    builder = sprite.blocks
    hat = builder.add("event_whenflagclicked", top=True, x=260, y=20)
    forever = builder.add("control_forever", parent=hat)
    wait = builder.add("control_wait", parent=forever, inputs={"DURATION": builder.num(max(0.01, 1.0 / max(1.0, float(fps))))})
    condition = builder.add("control_if", parent=wait)
    equals = builder.add("operator_equals", parent=condition)
    reporter = builder.add("data_variable", parent=equals, fields={"VARIABLE": [play_var, play_id]})
    builder.blocks[equals]["inputs"]["OPERAND1"] = [2, reporter]
    builder.blocks[equals]["inputs"]["OPERAND2"] = builder.num(1)
    next_costume = builder.add("looks_nextcostume", parent=condition)
    builder.blocks[hat]["next"] = forever
    builder.blocks[forever]["inputs"]["SUBSTACK"] = [2, wait]
    builder.blocks[wait]["next"] = condition
    builder.blocks[condition]["inputs"]["CONDITION"] = [2, equals]
    builder.blocks[condition]["inputs"]["SUBSTACK"] = [2, next_costume]


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
        report.translated.append(f"Detected SWF v{runtime.swf_version}: ActionScript 1/2 / AVM1")
    elif runtime.vm == "avm2":
        report.translated.append(f"Detected SWF v{runtime.swf_version}: ActionScript 3 / AVM2")
    else:
        report.warnings.append(f"SWF v{runtime.swf_version} contains no ActionScript bytecode FFDec could identify; timeline/assets will still be converted.")
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
    requested_frames = choose_frame_numbers(total_frames, program.text) if total_frames > 0 else None
    export_selected_frames(exe, swf, result, requested_frames)
    frames = _pngs(result.frames)
    rendered_numbers = _exported_frame_numbers(frames, requested_frames)
    if total_frames <= 0:
        total_frames = max(rendered_numbers, default=len(frames))
    plan = compact_frames(frames, program.text, frame_numbers=rendered_numbers, total_frames=total_frames)
    report.timeline_frames_exported = plan.original_count
    report.timeline_frames_rendered = plan.rendered_count
    report.timeline_unique_frames = plan.unique_count
    report.frame_assets = plan.kept_count
    report.duplicate_frames_removed = plan.duplicates_removed
    report.sampled_frames_removed = max(0, plan.original_count - plan.kept_count - plan.duplicates_removed)
    report.estimated_backdrop_memory_mb = plan.estimated_decoded_bytes / (1024 * 1024)
    for selected in plan.selected:
        project.add_stage_costume(selected.path, f"frame {selected.original_index}")
    if not frames:
        report.warnings.append("FFDec exported no main-timeline frame PNGs; using a blank stage.")
    elif plan.kept_count < plan.original_count:
        report.translated.append(f"Timeline compacted: {plan.original_count} Flash frames -> {plan.kept_count} Scratch backdrops")
        report.warnings.append("Long timeline compacted for Scratch/Chrome safety; omitted frames map to nearby retained backdrops.")

    symbol_cache: dict[int, list[Path]] = {}
    used_names: set[str] = set()
    reconstructed = 0
    truncated = False
    for requested_name, cid, script_referenced in _symbol_candidates(info, program):
        if reconstructed >= MAX_RECONSTRUCTED_SYMBOLS:
            truncated = True
            break
        name = _unique_name(requested_name, used_names)
        paths: list[Path] = []
        if cid is not None:
            if cid not in symbol_cache:
                symbol_cache[cid] = symbol_frames(result.root, cid)
            paths = symbol_cache[cid]
        if not paths and not script_referenced:
            continue
        sprite = project.sprite(name)
        if paths:
            sprite.costumes = [Asset(path.read_bytes(), "png", f"frame {index}") for index, path in enumerate(paths, 1)]
            report.sprite_assets += len(paths)
            _install_symbol_animation(project, sprite, name, info.frame_rate)
        reconstructed += 1
    if reconstructed:
        report.translated.append(f"Reconstructed {reconstructed} placed/named Flash symbol sprites")
    if truncated:
        report.warnings.append(f"Display-list reconstruction capped at {MAX_RECONSTRUCTED_SYMBOLS} symbols to keep the Scratch project responsive.")

    AS3Compiler(
        project,
        program,
        report,
        info.frame_rate,
        frame_map=plan.frame_map,
        stage_width=info.width,
        stage_height=info.height,
    ).compile()
    project.save(output)
    try:
        report.output_size_mb = output.stat().st_size / (1024 * 1024)
    except OSError:
        pass
    output.with_suffix(output.suffix + ".report.txt").write_text(report.text(), encoding="utf-8")
