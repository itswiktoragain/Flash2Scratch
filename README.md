# Flash2Scratch

Flash2Scratch is an experimental Python compiler that converts **Flash SWF games using ActionScript 1, 2, or 3** into **Scratch 3 `.sb3` projects** which can be opened in the normal Scratch editor.

It uses JPEXS Free Flash Decompiler (FFDec) as the SWF extraction/decompilation front-end, then translates supported Flash code and assets into native Scratch 3 blocks, sprites, backdrops, variables, and project data.

## Supported Flash runtimes

Flash2Scratch now detects the runtime instead of assuming every SWF is AS3:

- **AVM1 / ActionScript 1–2** — including Flash 8-era SWFs.
- **AVM2 / ActionScript 3** — normally Flash Player 9 and later.
- Scriptless SWFs are still accepted for timeline/asset conversion.

A Flash 8 game is normally AVM1/ActionScript 2 and does **not** contain `DoABC`; that is valid and is no longer rejected.

## Current conversion support

- Validates the SWF header and reports the SWF version.
- Detects AVM1 (`DoAction` / `DoInitAction`) and AVM2 (`DoABC`).
- Uses FFDec to export scripts, frames, sprites, sounds, symbol information, and SWF XML.
- Packages a real Scratch 3 ZIP/SB3 with `project.json` and MD5-addressed assets.
- Preserves exported main-timeline frames as Scratch backdrops.
- Best-effort named Flash display-object sprite mapping.
- AS3 event support includes `Event.ENTER_FRAME`, `MouseEvent.CLICK`, and common `KeyboardEvent.KEY_DOWN` handlers.
- Flash 8 / AS2 support includes common `onEnterFrame`, `onRelease`, `onPress`, `onClipEvent`, `_root`, `_x`, `_y`, `_rotation`, and `Key.isDown(...)` patterns.
- Common x/y/rotation and variable changes are translated where practical.
- `gotoAndStop`, `gotoAndPlay`, `nextFrame`, and `trace(...)` have Scratch mappings.
- A `.report.txt` is emitted listing unsupported or approximated code instead of silently deleting it.
- Includes a CLI and a PySide6 desktop UI.

## Important scope

There is no exact one-to-one mapping between arbitrary Flash code and Scratch. Flash exposes APIs and runtime behavior that Scratch simply does not have. Flash2Scratch therefore uses a growing compiler approach and reports anything it cannot faithfully represent.

Timeline games with named MovieClips, straightforward variables, keyboard/mouse input, and ordinary frame logic are the best targets today.

## Requirements

- Python 3.10+
- PySide6 for the desktop UI.
- Java, because FFDec itself runs on Java.

**You do not need to manually install FFDec for the desktop app.** If FFDec is missing, Flash2Scratch downloads the latest stable portable FFDec release from the official JPEXS GitHub releases and caches it in your user app-data folder.

## Install

```bash
python -m pip install -e '.[gui]'
```

## Run the desktop app

```bash
python main.py
```

or after installation:

```bash
flash2scratch-gui
```

Choose a `.swf`, choose the output `.sb3`, and click **Convert to Scratch 3**. The UI shows the detected runtime, for example:

```text
Detected SWF v8 — ActionScript 1/2 / AVM1
```

## CLI

```bash
flash2scratch game.swf game.sb3
```

To use a particular FFDec executable:

```bash
flash2scratch game.swf game.sb3 --ffdec /path/to/ffdec
```

Then open the resulting `.sb3` with **File → Load from your computer** in Scratch 3.

## Architecture

1. `ffdec.py` validates the SWF, detects AVM1/AVM2, auto-installs FFDec for the GUI, and extracts assets/source.
2. `as2.py` parses common AVM1/ActionScript 1–2 patterns.
3. `as3.py` parses common AVM2/ActionScript 3 patterns.
4. `swfxml.py` reads stage metadata and named `PlaceObject` IDs.
5. `compiler.py` translates normalized Flash logic into native Scratch blocks/state.
6. `sb3.py` serializes Scratch targets, blocks, variables and MD5-addressed assets into `.sb3`.
7. `converter.py` routes each SWF through the correct parser and writes the conversion report.

## Development

```bash
python -m pip install -e '.[dev,gui]'
pytest -q
```

## Legal note

Only convert SWFs you have permission to use. Flash2Scratch does not grant rights to redistribute code or assets from third-party SWFs.
