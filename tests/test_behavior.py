import json
import zipfile
from pathlib import Path

from flash2scratch.as2 import parse_sources as parse_as2_sources
from flash2scratch.ascode import parse_statements
from flash2scratch.compiler import AS3Compiler
from flash2scratch.sb3 import Asset, ScratchProject


class Report:
    def __init__(self):
        self.translated = []
        self.unsupported = []


def _program(tmp_path: Path, source: str):
    scripts = tmp_path / "scripts" / "frame1"
    scripts.mkdir(parents=True)
    (scripts / "DoAction.as").write_text(source, encoding="utf-8")
    return parse_as2_sources(tmp_path / "scripts")


def test_statement_parser_handles_control_flow():
    statements = parse_statements(
        "if (score < 3) { score++; } else { score = 0; } "
        "for (var i=0; i<3; i++) { score += i; }"
    )
    assert [item.kind for item in statements] == ["if", "for"]
    assert statements[0].else_body
    assert statements[1].init and statements[1].update


def test_flash8_frame_script_is_not_dropped(tmp_path: Path):
    scripts = tmp_path / "scripts" / "frame12"
    scripts.mkdir(parents=True)
    (scripts / "DoAction.as").write_text("stop(); score = 5;", encoding="utf-8")
    program = parse_as2_sources(tmp_path / "scripts")
    assert len(program.frame_scripts) == 1
    assert program.frame_scripts[0].frame == 12
    assert "score = 5" in program.frame_scripts[0].body


def test_clip_event_owner_can_come_from_ffdec_path(tmp_path: Path):
    scripts = tmp_path / "scripts" / "player"
    scripts.mkdir(parents=True)
    (scripts / "ClipAction.as").write_text(
        "onClipEvent(enterFrame) { _x += 2; }", encoding="utf-8"
    )
    program = parse_as2_sources(tmp_path / "scripts")
    assert program.listeners
    assert program.listeners[0].owner == "player"
    assert "player" in program.display_objects


def test_behavior_compiler_generates_real_game_blocks(tmp_path: Path):
    program = _program(
        tmp_path,
        """
        var score = 0;
        var a = [];
        stop();
        function move(n) { player._x += n; }
        a.push(3);
        a.push(4);
        player.onEnterFrame = function() {
            if (Key.isDown(Key.LEFT)) { _x -= 5; }
            if (score < 10 && a.length > 0) { score++; }
            else { score = 0; }
        };
        for (var i=0; i<3; i++) { a[i] = i * 2; }
        move(3);
        """,
    )

    project = ScratchProject()
    project.stage.costumes = [
        Asset(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "svg", "frame 1"),
        Asset(b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>', "svg", "frame 2"),
    ]
    report = Report()
    AS3Compiler(
        project,
        program,
        report,
        fps=24,
        frame_map={1: "frame 1", 2: "frame 2"},
        stage_width=550,
        stage_height=400,
    ).compile()

    opcodes = {block["opcode"] for block in project.stage.blocks.blocks.values()}
    for sprite in project.sprites.values():
        opcodes.update(block["opcode"] for block in sprite.blocks.blocks.values())

    assert {
        "control_if_else",
        "control_repeat_until",
        "control_forever",
        "data_addtolist",
        "event_broadcastandwait",
        "motion_setx",
        "looks_nextbackdrop",
    } <= opcodes
    assert project.stage.lists
    assert project.stage.broadcasts
    assert not report.unsupported


def test_behavior_project_serializes_lists_and_broadcasts(tmp_path: Path):
    program = _program(tmp_path, "var a=[]; a.push(3); function ping(){ score += 1; } ping();")
    project = ScratchProject()
    report = Report()
    AS3Compiler(project, program, report).compile()
    output = tmp_path / "behavior.sb3"
    project.save(output)

    with zipfile.ZipFile(output) as archive:
        data = json.loads(archive.read("project.json"))
    stage = data["targets"][0]
    assert stage["lists"]
    assert stage["broadcasts"]
