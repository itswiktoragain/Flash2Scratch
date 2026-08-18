import json
import re
import struct
import zipfile
from pathlib import Path

from flash2scratch.as2 import parse_sources as parse_as2_sources
from flash2scratch.as3 import parse_sources
from flash2scratch.ffdec import swf_version
from flash2scratch.frames import compact_frames, referenced_frame_numbers
from flash2scratch.sb3 import ScratchProject


def test_parse_as3(tmp_path: Path):
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "Main.as").write_text(
        "function k(e:KeyboardEvent):void { player.x -= 5; } "
        "stage.addEventListener(KeyboardEvent.KEY_DOWN,k); "
        "var score:int=2; var player:MovieClip;"
    )
    p = parse_sources(d)
    assert "k" in p.handlers
    assert p.variables["score"] == "2"
    assert "player" in p.display_objects


def test_parse_flash8_as2(tmp_path: Path):
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "Main.as").write_text(
        "var score = 2; player.onEnterFrame = function() { "
        "if (Key.isDown(Key.LEFT)) { player._x -= 5; } }; "
        "button.onRelease = function() { score += 1; };"
    )
    p = parse_as2_sources(d)
    assert p.variables["score"] == "2"
    assert "player" in p.display_objects
    assert any(x.event == "Event.ENTER_FRAME" for x in p.listeners)
    assert any(x.event == "MouseEvent.CLICK" for x in p.listeners)


def test_swf8_header_is_valid(tmp_path: Path):
    f = tmp_path / "old.swf"
    f.write_bytes(b"FWS" + bytes([8]) + b"placeholder")
    assert swf_version(f) == 8


def _fake_png(width: int, height: int, marker: bytes) -> bytes:
    # Enough PNG header/IHDR bytes for the frame planner's dimension reader.
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + marker


def test_frame_compaction_deduplicates_and_caps(tmp_path: Path):
    frames = []
    for index in range(1, 13):
        path = tmp_path / f"frame{index}.png"
        # Frames 1/2 and 7/8 are exact duplicates.
        marker_number = 1 if index == 2 else 7 if index == 8 else index
        path.write_bytes(_fake_png(480, 360, bytes([marker_number])))
        frames.append(path)

    plan = compact_frames(
        frames,
        "gotoAndStop(9); gotoAndPlay(4);",
        max_backdrops=5,
        decoded_memory_mb=128,
    )
    assert plan.original_count == 12
    assert plan.unique_count == 10
    assert plan.duplicates_removed == 2
    assert plan.kept_count <= 5
    assert plan.frame_map[9] == "frame 9"
    assert plan.frame_map[4] == "frame 4"
    assert plan.frame_map[2] == plan.frame_map[1]


def test_memory_budget_reduces_large_backdrops(tmp_path: Path):
    frames = []
    for index in range(1, 20):
        path = tmp_path / f"large{index}.png"
        path.write_bytes(_fake_png(1920, 1080, bytes([index])))
        frames.append(path)

    plan = compact_frames(frames, max_backdrops=180, decoded_memory_mb=32)
    assert plan.kept_count < len(frames)
    assert plan.estimated_decoded_bytes <= 40 * 1024 * 1024


def test_referenced_frame_parser():
    assert referenced_frame_numbers("gotoAndStop(12); _root.gotoAndPlay(44);") == {12, 44}


def test_sb3(tmp_path: Path):
    p = ScratchProject()
    p.global_var("score", 0)
    p.sprite("player")
    output = tmp_path / "x.sb3"
    p.save(output)
    with zipfile.ZipFile(output) as z:
        project = json.loads(z.read("project.json"))
        assert project["meta"]["semver"] == "3.0.0"
        assert re.match(r"^[0-9]+\.[0-9]+\.[0-9]+($|-)", project["meta"]["vm"])
        assert all(
            costume["md5ext"] in z.namelist()
            for target in project["targets"]
            for costume in target["costumes"]
        )
