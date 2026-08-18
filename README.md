# Flash2Scratch

Flash2Scratch is an experimental Python compiler that converts **ActionScript 3 / AVM2 SWF files** into **Scratch 3 `.sb3` projects** which can be opened in the normal Scratch editor.

It extracts a SWF with JPEXS Free Flash Decompiler (FFDec), translates parts of ActionScript 3 that have reasonable Scratch equivalents, preserves timeline visuals as Scratch backdrops, creates Scratch sprite proxies for named Flash display objects, and writes a native Scratch 3 project.

## What works in 0.1

- Verifies AVM2 / `DoABC` ActionScript 3 bytecode.
- Uses FFDec to export AS3 source, timeline frames, sprites, sounds and SWF XML.
- Packages a real Scratch 3 ZIP/SB3 with `project.json` and MD5-addressed assets.
- Preserves exported main-timeline frames as Scratch backdrops.
- Best-effort named Flash display-object sprite mapping.
- Recognizes `Event.ENTER_FRAME`, `MouseEvent.CLICK`, and common `KeyboardEvent.KEY_DOWN` listeners.
- Translates common x/y/rotation/visibility/alpha/scale and variable changes.
- Translates `gotoAndStop`, `gotoAndPlay`, `nextFrame`, and `trace(...)` where practical.
- Emits a `.report.txt` listing unsupported or approximated AS3 instead of silently dropping it.
- Includes a CLI and optional PySide6 GUI.

## Important scope

There is no exact one-to-one mapping between arbitrary ActionScript 3 and Scratch. Flash has classes/inheritance, dynamic display lists, filters, BitmapData, networking, Stage3D, reflection, dynamically loaded SWFs, AIR APIs, and many other features Scratch cannot reproduce directly.

Flash2Scratch therefore uses a growing compiler approach. Timeline games with named MovieClips, keyboard/mouse events, and straightforward game-state logic are the best targets.

## Requirements

- Python 3.10+
- JPEXS Free Flash Decompiler (FFDec). Put `ffdec` / `ffdec.sh` in `PATH`, set `FFDEC`, or pass `--ffdec`.

FFDec is only the SWF/AVM2 extraction front-end; the Scratch compiler and SB3 writer are Python code in this repository.

## Install

```bash
python -m pip install -e .
```

Optional GUI:

```bash
python -m pip install -e '.[gui]'
```

Development/tests:

```bash
python -m pip install -e '.[dev]'
pytest -q
```

## Convert

```bash
flash2scratch game.swf game.sb3
```

If FFDec is not in PATH:

```bash
flash2scratch game.swf game.sb3 --ffdec /path/to/ffdec
```

Keep intermediate exports:

```bash
flash2scratch game.swf game.sb3 --keep-temp ffdec-export
```

Then open the resulting `.sb3` with **File → Load from your computer** in Scratch 3.

## Desktop app

```bash
flash2scratch-gui
```

## Architecture

1. `ffdec.py` validates `DoABC` and exports AS3/assets/XML.
2. `swfxml.py` reads stage metadata and named `PlaceObject` IDs.
3. `as3.py` extracts AS3 functions, variables, display-object references and event listeners.
4. `compiler.py` translates the supported AS3 subset into native Scratch blocks/state.
5. `sb3.py` serializes Scratch targets, blocks, variables and MD5-addressed assets into `.sb3`.
6. `converter.py` connects the pipeline and writes a conversion report.

## Planned work

- Proper AS3 AST parser.
- Arithmetic/comparison/boolean expressions.
- `if/else`, loops, `switch`, and function/custom-block translation.
- Better display-list reconstruction.
- Sounds / `SoundChannel`.
- `hitTestObject` / `hitTestPoint` collision mapping.
- Mouse position/buttons and dragging.
- TextField mapping.
- Arrays/Vectors to Scratch lists.
- Frame labels/scenes and more faithful timeline scheduling.

## Legal note

Only convert SWFs you have permission to use. Flash2Scratch does not grant rights to redistribute code or assets from third-party SWFs.
