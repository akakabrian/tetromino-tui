# tetromino-tui

> Inspired by Tetris (1985, Alexey Pajitnov). Trademarks belong to their respective owners. Unaffiliated fan project.

One line at a time.

![Hero](screenshots/hero.svg)
![Gameplay](screenshots/gameplay.svg)
![End screen](screenshots/endscreen.svg)

## About
SRS rotations with real wall kicks. A proper 7-bag randomizer. Hold piece, next queue, level speed ramp, mouse + keyboard. The block-stacker that has no ending — just a thinner and thinner layer of hope between you and the top-out.

## Screenshots
![Hero](screenshots/hero.svg)
![Gameplay](screenshots/gameplay.svg)
![End screen](screenshots/endscreen.svg)

## Install & Run
```bash
git clone https://github.com/akakabrian/tetromino-tui
cd tetromino-tui
make
make run
```

Run with music enabled:
```bash
make run ARGS="--music"
# or:
.venv/bin/python play.py --music
```

Run muted (no SFX):
```bash
make run ARGS="--no-sound"
```

## Updating
```bash
cd tetromino-tui
make update
make run
```

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
| `m`        | toggle music             |
| `?`        | help overlay             |
| `q`        | quit                     |

## Music credits
- Chiptune Tchaikovsky — Tomasz Kucza, [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Cyberpunk Moonlight Sonata — Joth, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)

## Testing
```bash
make test       # QA harness
make playtest   # scripted critical-path run
make perf       # performance baseline
```

## License
MIT

## Built with
- [Textual](https://textual.textualize.io/) — the TUI framework
- [tui-game-build](https://github.com/akakabrian/tui-foundry) — shared build process
