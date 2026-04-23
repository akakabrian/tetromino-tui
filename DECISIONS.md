# Design decisions — tetris-tui ("Terminal Blocks")

## 0. Licensing stance

Tetris is an Alexey Pajitnov / The Tetris Company trademark. We build
clean-room from public specs (the [Tetris Guideline][guideline] on the
Tetris Wiki, the well-known SRS rotation / kick tables), **without**
using any Tetris-Company assets, copy, sound, or marketing imagery. Same
pattern as Julius/Karateka/FF1 clones: the mechanic is unprotectable,
the brand is not.

Rule: **the package, README, and in-game UI name the game "Terminal
Blocks"**. Docs and code comments may reference "Tetris" as the
mechanic-family for clarity — that's fair descriptive use — but the
shipped UI chrome never does. If we later want to publish publicly
under a different name we flip a single string constant.

[guideline]: https://tetris.wiki/Tetris_Guideline

## 1. Engine: pure-Python, no native binding

Same reasoning as the 2048-tui DECISIONS doc: Tetris rules are ~200
lines of Python (board, piece, SRS kicks, line clear, gravity) and
implementing them is faster than vendoring + SWIG-binding a C engine
for zero algorithmic gain. The stage-2 "one import, one tick, one
render" gate passes trivially.

We keep the SWIG-binding *shape* of the API though — `Game.tick()`,
`Game.state()`, `Game.action(name)` — so everything downstream
(TUI, QA, agent API if we add one) looks like every other skill-canon
project.

## 2. Playfield dimensions

Standard Tetris Guideline playfield: **10 columns × 20 visible rows**,
plus **2 hidden buffer rows above** for piece spawns (so an I-piece
spawning horizontally can always fit even if the topmost visible row
is already occupied). Internally the matrix is 10×22; the renderer
draws rows 2..21.

The top two hidden rows are *part of the game-over check*: if any tile
of a newly-spawned piece overlaps filled cells (including buffer rows),
the game ends. That's the classic lock-out rule.

## 3. The 7 pieces + SRS rotation

Seven tetrominoes — I, O, T, S, Z, J, L — each with four rotation
states (R0, R, R2, R'), expressed as 4-cell coordinate offsets from a
piece-local origin.

**Rotation system: SRS (Super Rotation System).** Rotation attempts
apply the base offsets; if any cell collides, we try up to 5 **wall
kick** offsets from the SRS kick tables. Two kick tables:

  * JLSTZ kicks — shared by J, L, S, T, Z
  * I kicks — the I piece rotates around a different center

The O piece has no effective rotation (it's a square) but we still
accept rotate presses as no-ops so the input contract stays clean.

See `tetris_tui/pieces.py` for the canonical offset tables, sourced
from the Tetris Wiki SRS article.

## 4. Randomizer: 7-bag

Classic **7-bag shuffle** (Random Generator). At game start and every
time the bag empties, we shuffle the 7 piece letters into a new bag.
This guarantees "no more than 12 pieces between two of the same", the
Guideline's anti-frustration rule. Next-queue shows the next 5 pieces.

## 5. Hold

Single-slot hold register. Swap-once-per-piece rule — after holding,
the player can't hold again until they lock a piece. Matches the
Guideline. If hold is empty the current piece goes there and the next
piece from the bag becomes active.

## 6. Gravity curve

Guideline-derived curve: gravity increases each level up to ~20G. We
use the Tetris Worlds formula:

    frames_per_row = (0.8 − (level − 1) × 0.007) ** (level − 1)
                     * 60   # converted to a 60 Hz frame budget

For levels beyond ~15 this drops below 1 frame/row — we treat that as
"20G" (piece drops to its landing row on spawn). Implementation stores
gravity as a float accumulator; each tick adds `1/frames_per_row` and
every whole unit pushes one row down.

Soft drop = 20× gravity (the Guideline default). Hard drop = instant
lock.

Lock delay: 500 ms (30 frames at 60 Hz) on touch-ground; any movement
or rotation resets the timer up to 15 times ("infinity") before forced
lock — this matches the Guideline's "move-reset" infinity rule.

## 7. Scoring

Guideline base values × level:

  * Single line  = 100
  * Double lines = 300
  * Triple lines = 500
  * Tetris (4)   = 800
  * Back-to-back tetris / T-spin bonus = base × 1.5 (stretch goal)
  * Soft drop    = 1 pt per cell manually dropped
  * Hard drop    = 2 pts per cell dropped

Level up every 10 lines cleared.

## 8. T-spin detection (stretch, preserve if scope allows)

Three-corner T-spin detection: after a rotation that used a kick and
three or more of the T-piece's corner cells are filled, award a T-spin
bonus. Skipped in the initial implementation; the hook is left in
`Game._last_rotation_kicked` so we can wire it up in Phase E.

## 9. Persistence

`$XDG_DATA_HOME/tetris-tui/state.json` (falls back to
`~/.local/share/tetris-tui/`). Schema:

    {
      "high_scores": [
        {"score": 12345, "lines": 54, "level": 6, "date": "2026-04-23"}
      ],
      "settings": {"sound": false, "ghost": true}
    }

Top 10 high scores persisted. Ghost-piece preference persists across
sessions.

## 10. UI layout

Four-panel Textual layout:

  * **Matrix** — the 10×20 playfield, center-left, 2 cells wide per
    block (so the grid reads square).
  * **Next queue** — 5 stacked upcoming pieces, right side top.
  * **Hold** — single piece slot, right side below next.
  * **Stats** — score / lines / level / time, right side bottom.

Status bar under the matrix shows last-clear text ("single / double /
TETRIS!") briefly, and game-state (PAUSED / GAME OVER) when active.

## 11. Controls

  * **← →**   move left / right
  * **↓**    soft drop
  * **space** hard drop
  * **z**    rotate CCW
  * **x** or **↑**    rotate CW
  * **c**    hold
  * **p**    pause
  * **n**    new game (confirm if mid-game with real score)
  * **?**    help overlay
  * **q**    quit

Arrows are `priority=True` App bindings so scrollable widgets don't
eat them.

## 12. Textual version pin

`textual>=0.80,<10` — same pin as 2048-tui / simcity-tui. Textual 10
has changed the animation frame hook shape that we depend on.

## 13. Stage-7 phases scoped

Following the tui-game-build phased-polish list:

  * **Phase A (UI beauty)** — per-piece colors, ghost piece (dim
    outline of where the piece would land), lock flash, line-clear
    flash animation frames.
  * **Phase B (submenus)** — help overlay, high-score table modal,
    game-over modal with score submission.
  * **Phase C (agent REST API)** — **skipped initially**. Tetris has
    a small action space (L/R/down/rotate/drop/hold = 7 verbs) but
    RL-style Tetris bots already exist; we only wire this if scope
    permits.
  * **Phase D (sound)** — synth blips for move / rotate / lock /
    clear / tetris / gameover. Off by default.
  * **Phase E (polish)** — T-spin detection + back-to-back bonus,
    level-up flash, starting-level selector.
  * **Phase F (animation)** — piece-slide animation (cheap, piece
    only occupies 4 cells), line-clear row-flash (2 frames of bright
    before collapse).
  * **Phase G (LLM advisor)** — skipped. Tetris advice is trivial
    positional analysis, not worth API spend.

## 14. Known gotchas we respect up front

From the tui-game-build skill catalog:

  * Arrow bindings are `priority=True` on the App so scrolling widgets
    don't swallow them.
  * Never name a method `_render*` on a Textual Widget subclass — use
    `_refresh_body` / `_build_strip` / `_compose_*`.
  * Modal screen keys avoid arrows and enter; we use `y/n/escape`
    inside confirm modals.
  * `Static("", id=...)` everywhere — never `Static(id=...)` alone.
  * `list(strip)` in tests, never `strip._segments`.
  * Reactive watchers guarded with `if not self.is_mounted: return`
    when they touch display state.
