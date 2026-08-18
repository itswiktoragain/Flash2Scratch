# Flash2Scratch

Flash2Scratch is an experimental Python compiler that converts **Flash SWF games using ActionScript 1, 2, or 3** into **Scratch 3 `.sb3` projects**.

It uses JPEXS Free Flash Decompiler (FFDec) only as the SWF/decompiler front-end. Flash2Scratch itself reconstructs the display list, translates supported ActionScript into native Scratch blocks, compacts Flash timelines into Scratch-friendly assets, and writes the final SB3.

## Supported Flash runtimes

- **AVM1 / ActionScript 1–2** — including Flash 8-era SWFs.
- **AVM2 / ActionScript 3** — normally Flash Player 9 and later.
- Scriptless SWFs are accepted for timeline/asset conversion.

A Flash 8 game normally uses AVM1 and does **not** contain `DoABC`; that is valid.

## 0.5 behavior compiler

0.5 focuses on recreating code rather than merely extracting media.

- Flash/AS2 **frame scripts are compiled and executed** instead of being silently ignored.
- Main Flash timelines are driven at the SWF frame rate and respond to `stop()`, `play()`, `gotoAndStop()`, `gotoAndPlay()`, `nextFrame()`, and `prevFrame()`.
- `if/else`, `while`, `do/while`, and common `for` loops become Scratch control blocks.
- Arithmetic, comparisons, boolean operators, variables, increments, and compound assignments become native Scratch reporters/data blocks.
- Common helper functions are recreated using synchronous Scratch broadcasts; ActionScript parameters are passed through generated argument variables.
- `Key.isDown(...)` becomes continuous Scratch key sensing inside frame/update logic.
- Flash `_x`, `_y`, `_rotation`, `_visible`, `_alpha`, and scale properties map to real Scratch motion/looks behavior, including cross-sprite property writes.
- Flash top-left coordinates are translated to Scratch center-origin coordinates using the detected SWF stage dimensions.
- Common AS2 arrays become Scratch lists, with support for indexed reads/writes, `.length`, `push`, `pop`, `shift`, and `unshift`.
- Common math/runtime reporters include `Math.*`, `random`, `getTimer`, and basic scalar conversions.
- Basic `hitTest` behavior maps to Scratch touching checks when there is a direct equivalent.
- Unsupported behavior is listed in the conversion report instead of disappearing silently.

The converter no longer exports every sound during the core pass when those files are not going to be attached to the generated Scratch project.

## Display-list and timeline reconstruction

- Named and placed Flash MovieClips/buttons are reconstructed as Scratch sprites when FFDec exports a corresponding symbol.
- Sprite assets are matched by FFDec character-ID directories, avoiding collisions between unrelated `1.png` animation frames.
- Multi-frame MovieClips receive pausable costume timelines.
- Long main timelines use selective FFDec frame rendering, duplicate removal, sampling, and a decoded-memory budget so a small vector SWF does not become a browser-killing SB3.
- Numeric Flash frame jumps are remapped to retained Scratch backdrops when timeline compaction is necessary.

## Important scope

Flash and Scratch runtimes are fundamentally different, so arbitrary ActionScript cannot always be represented exactly. Features with no Scratch equivalent are approximated when reasonable and otherwise reported in `.sb3.report.txt`.

Flash 8 timeline games using ordinary MovieClips, variables, keyboard/mouse input, frame scripts, helper functions, and straightforward game loops are the strongest targets.

## Requirements

- Python 3.10+
- PySide6 for the desktop UI
- Java, because FFDec runs on Java

**You do not need to manually install FFDec for the desktop app.** If FFDec is missing, Flash2Scratch downloads the latest stable portable FFDec release from the official JPEXS GitHub releases and caches it in your user app-data folder.

## Install and run

```bash
python -m pip install -e '.[gui]'
python main.py
```

Or after installation:

```bash
flash2scratch-gui
```

CLI:

```bash
flash2scratch game.swf game.sb3
```

## Architecture

1. `ffdec.py` validates SWFs, detects AVM1/AVM2, and manages FFDec.
2. `ffdec_export.py` performs staged/selective exports.
3. `as2.py` / `as3.py` recover ActionScript programs and events.
4. `ascode.py` parses ActionScript statements and expressions into a small internal representation.
5. `behavior_expr.py` and `behavior_stmt.py` translate expressions/statements to native Scratch blocks.
6. `behavior_compiler.py` recreates timelines, frame scripts, events, helper functions, input, and state.
7. `swfxml.py` / `symbols.py` reconstruct stage metadata and Flash symbol instances.
8. `sb3.py` writes the native Scratch 3 project.
9. `converter.py` coordinates the complete conversion and emits a report.

## Development

```bash
python -m pip install -e '.[dev,gui]'
pytest -q
```

## Legal note

Only convert SWFs you have permission to use. Flash2Scratch does not grant rights to redistribute code or assets from third-party SWFs.
