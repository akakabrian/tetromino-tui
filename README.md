# tetris-tui ("Terminal Blocks")

Clean-room terminal Tetris-family game built with [Textual].

A 10×20 matrix, seven tetrominoes, SRS rotation with wall kicks, a
7-bag randomizer, hold, next-queue, ghost piece, soft/hard drop, lock
delay with move-reset infinity, back-to-back tetris bonus, level-curve
gravity, and a persistent top-10 high-score table.

Playfield: 10×20 visible + 2 hidden buffer rows. 7 tetrominoes
(I/O/T/S/Z/J/L). Rotation system: **SRS** with full wall-kick tables.
Scoring: single/double/triple/tetris = 100/300/500/800 × level,
back-to-back tetris × 1.5. Soft drop 1 pt/cell, hard drop 2 pts/cell.

See `DECISIONS.md` for the design rationale and the licensing stance.
**"Terminal Blocks" is the shipped UI name** — Tetris is an Alexey
Pajitnov / Tetris Company trademark and we don't reuse any
Tetris-Company assets.

## Quick start

```bash
make            # create venv + install
make run        # play
make test       # run the QA harness (39 scenarios)
make perf       # print performance baseline
```

Requires Python ≥3.10. Textual is the only runtime dependency.

## Controls

| key        | action                   |
|-----------:|:-------------------------|
| `← →`      | move left/right          |
| `↓`        | soft drop (+1/cell)      |
| `space`    | hard drop (+2/cell)      |
| `z`        | rotate counter-clockwise |
| `x` or `↑` | rotate clockwise         |
| `c`        | hold / swap              |
| `p`        | pause                    |
| `n`        | new game                 |
| `h`        | high-score table         |
| `g`        | toggle ghost piece       |
| `s`        | toggle sound             |
| `?`        | help overlay             |
| `q`        | quit                     |

## Architecture

Pure-Python engine (`tetris_tui/engine.py`), Textual 4-panel UI
(`tetris_tui/app.py`), modal screens (`tetris_tui/screens.py`),
synth sounds (`tetris_tui/sounds.py`), XDG-dir persistence
(`tetris_tui/state.py`). No native binding — DECISIONS.md §1 explains
why the `tui-game-build` skill's SWIG recipe is unnecessary here.

Tests drive the app through Textual's `Pilot` and assert on live
engine state; each scenario saves an SVG screenshot under `tests/out/`.

## Licensing

Code: MIT (wrapper). The mechanic is inspired by Tetris; no
Tetris-Company assets are used or redistributed.

[Textual]: https://textual.textualize.io/
