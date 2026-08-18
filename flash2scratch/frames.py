from __future__ import annotations

import bisect
import hashlib
import re
import struct
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MAX_BACKDROPS = 180
DEFAULT_DECODED_MEMORY_MB = 128
_MIN_BACKDROPS = 8


@dataclass(frozen=True)
class SelectedFrame:
    original_index: int
    path: Path


@dataclass
class FramePlan:
    selected: list[SelectedFrame]
    frame_map: dict[int, str]
    original_count: int
    unique_count: int
    duplicates_removed: int
    sampled_out: int
    effective_cap: int
    estimated_decoded_bytes: int

    @property
    def kept_count(self) -> int:
        return len(self.selected)


def referenced_frame_numbers(source_text: str) -> set[int]:
    """Return statically referenced numeric gotoAndStop/gotoAndPlay frames."""
    refs: set[int] = set()
    pattern = re.compile(
        r"\bgotoAnd(?:Stop|Play)\s*\(\s*([0-9]+)\s*\)",
        re.I,
    )
    for match in pattern.finditer(source_text or ""):
        try:
            value = int(match.group(1))
        except ValueError:
            continue
        if value > 0:
            refs.add(value)
    return refs


def _hash_file(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError:
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        width, height = struct.unpack(">II", header[16:24])
    except struct.error:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _evenly_spaced(values: list[int], count: int) -> list[int]:
    if count <= 0 or not values:
        return []
    if count >= len(values):
        return list(values)
    if count == 1:
        return [values[len(values) // 2]]

    result: list[int] = []
    last = len(values) - 1
    for slot in range(count):
        index = round(slot * last / (count - 1))
        value = values[index]
        if value not in result:
            result.append(value)

    # round() can theoretically collide for tiny lists; fill any gap deterministically.
    if len(result) < count:
        for value in values:
            if value not in result:
                result.append(value)
                if len(result) == count:
                    break
    return sorted(result)


def _nearest(selected_indices: list[int], frame_index: int) -> int:
    position = bisect.bisect_left(selected_indices, frame_index)
    if position <= 0:
        return selected_indices[0]
    if position >= len(selected_indices):
        return selected_indices[-1]
    before = selected_indices[position - 1]
    after = selected_indices[position]
    return before if frame_index - before <= after - frame_index else after


def compact_frames(
    frames: list[Path],
    source_text: str = "",
    *,
    max_backdrops: int = DEFAULT_MAX_BACKDROPS,
    decoded_memory_mb: int = DEFAULT_DECODED_MEMORY_MB,
) -> FramePlan:
    """Build a Scratch-friendly timeline frame plan.

    FFDec may render thousands of full-frame PNGs from a very small vector SWF.
    Loading all of those as Scratch costumes can consume hundreds of MB or more
    after image decoding. This planner:

    * removes byte-identical frames from the costume list;
    * retains first/last and statically referenced numeric goto frames;
    * samples long unique runs evenly;
    * limits the result by both costume count and estimated decoded RGBA memory;
    * maps every original Flash frame to the nearest retained Scratch backdrop.
    """
    frames = list(frames)
    if not frames:
        return FramePlan([], {}, 0, 0, 0, 0, 0, 0)

    max_backdrops = max(_MIN_BACKDROPS, int(max_backdrops))
    budget_bytes = max(16, int(decoded_memory_mb)) * 1024 * 1024

    first_for_digest: dict[bytes, tuple[int, Path]] = {}
    canonical_for_frame: dict[int, int] = {}

    for index, path in enumerate(frames, 1):
        digest = _hash_file(path)
        first_for_digest.setdefault(digest, (index, path))
        canonical_for_frame[index] = first_for_digest[digest][0]

    unique = sorted(first_for_digest.values(), key=lambda item: item[0])
    unique_indices = [index for index, _ in unique]
    path_for_index = {index: path for index, path in unique}

    dimensions = _png_dimensions(unique[0][1]) if unique else None
    if dimensions:
        width, height = dimensions
        bytes_per_frame = max(1, width * height * 4)
        memory_cap = max(_MIN_BACKDROPS, budget_bytes // bytes_per_frame)
    else:
        memory_cap = max_backdrops

    effective_cap = max(_MIN_BACKDROPS, min(max_backdrops, int(memory_cap)))
    effective_cap = min(effective_cap, len(unique_indices))

    refs = {
        frame
        for frame in referenced_frame_numbers(source_text)
        if 1 <= frame <= len(frames)
    }
    mandatory = {
        canonical_for_frame[1],
        canonical_for_frame[len(frames)],
        *(canonical_for_frame[frame] for frame in refs),
    }

    # If a game statically jumps to more frames than our safety budget allows,
    # preserve an even subset and map the rest to their nearest retained frame.
    mandatory_sorted = sorted(mandatory)
    if len(mandatory_sorted) > effective_cap:
        selected_indices = set(_evenly_spaced(mandatory_sorted, effective_cap))
    else:
        selected_indices = set(mandatory_sorted)
        remaining_slots = effective_cap - len(selected_indices)
        candidates = [index for index in unique_indices if index not in selected_indices]
        selected_indices.update(_evenly_spaced(candidates, remaining_slots))

    selected_sorted = sorted(selected_indices)
    selected = [
        SelectedFrame(index, path_for_index[index])
        for index in selected_sorted
    ]

    frame_map: dict[int, str] = {}
    selected_set = set(selected_sorted)
    for original_index in range(1, len(frames) + 1):
        canonical = canonical_for_frame[original_index]
        if canonical in selected_set:
            mapped = canonical
        else:
            mapped = _nearest(selected_sorted, original_index)
        frame_map[original_index] = f"frame {mapped}"

    estimated_decoded = 0
    for frame in selected:
        dims = _png_dimensions(frame.path)
        if dims:
            estimated_decoded += dims[0] * dims[1] * 4

    unique_count = len(unique_indices)
    kept_count = len(selected)
    return FramePlan(
        selected=selected,
        frame_map=frame_map,
        original_count=len(frames),
        unique_count=unique_count,
        duplicates_removed=len(frames) - unique_count,
        sampled_out=max(0, unique_count - kept_count),
        effective_cap=effective_cap,
        estimated_decoded_bytes=estimated_decoded,
    )
