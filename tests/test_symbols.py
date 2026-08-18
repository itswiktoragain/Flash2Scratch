from pathlib import Path

from flash2scratch.swfxml import parse_swf_xml
from flash2scratch.symbols import symbol_frames


def _png(marker: bytes) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + marker


def test_symbol_matching_uses_character_directory_not_frame_filename(tmp_path: Path):
    root = tmp_path / "export"
    wrong = root / "sprites" / "2"
    right = root / "sprites" / "7"
    wrong.mkdir(parents=True)
    right.mkdir(parents=True)

    # Every FFDec sprite animation can have a frame named 1.png. The old
    # converter could therefore give character 7 an unrelated character's
    # first frame if it searched PNG stems instead of the character directory.
    (wrong / "1.png").write_bytes(_png(b"wrong"))
    (right / "1.png").write_bytes(_png(b"right-1"))
    (right / "2.png").write_bytes(_png(b"right-2"))

    frames = symbol_frames(root, 7)
    assert [path.parent.name for path in frames] == ["7", "7"]
    assert [path.name for path in frames] == ["1.png", "2.png"]


def test_xml_parser_distinguishes_top_level_and_nested_symbols(tmp_path: Path):
    xml = tmp_path / "movie.xml"
    xml.write_text(
        """
        <swf frameRate="24">
          <DefineSpriteTag characterId="7">
            <PlaceObject2Tag characterId="8" name="inner" depth="1" />
          </DefineSpriteTag>
          <DefineSpriteTag characterId="8" />
          <PlaceObject2Tag characterId="7" name="gameRoot" depth="3" />
          <PlaceObject2Tag characterId="8" depth="4" />
        </swf>
        """,
        encoding="utf-8",
    )

    info = parse_swf_xml(xml)
    assert info.frame_rate == 24
    assert info.sprite_ids == {7, 8}
    assert info.instances["inner"] == 8
    assert info.instances["gameRoot"] == 7

    nested = next(item for item in info.placements if item.name == "inner")
    root = next(item for item in info.placements if item.name == "gameRoot")
    anonymous = next(item for item in info.placements if item.name is None)

    assert nested.owner_character_id == 7
    assert not nested.top_level
    assert root.top_level
    assert anonymous.top_level
