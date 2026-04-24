# DOGFOOD — tetris-tui

_Session: 2026-04-23T09:24:15, driver: pilot, duration: 8.0 min_

## Summary

Ran a rule-based exploratory session via `pilot` driver. Found 2 UX note(s). Game reached 11 unique state snapshots.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)
- **[U1] help-screen discoverability not tested** (framework coverage note)
  - (explorer skipped `?` — unusual; `f1` was tried and appears to not open a
    help overlay, see phase-b-end snapshot)
  - Evidence: [007-phase-b-end.svg](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/007-phase-b-end.svg)
- **[U2] coverage self-report: 277 key presses across 24 unique keys** (framework coverage note)
  - Unique keys exercised: `,`, `2`, `4`, `R`, `[`, `]`, `b`, `c`, `down`, `enter`, `escape`, `f1`, `j`, `l`, `left`, `n`, `p`, `page_down`, `r`, `right`, `shift+tab`, `space`, `up`, `v`

## Session notes (not findings, but worth a look)

Pilot reached 11 unique game states across 41 samples, i.e. the explorer
cycled on the same board configurations for long stretches. Looking at the
snapshot timeline:

- Phase A start ([001](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/001-phase-a-start.svg)) → Phase A loop 20 ([005](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/005-phase-a-loop-20.svg)): rotate/translate/hard-drop loop, piece spawning behaved normally.
- Phase B ([006](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/006-phase-b-start.svg) → [007](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/007-phase-b-end.svg)): menu/submenu sweep (enter/escape + misc keys); no crashes, no stuck modals.
- Phase C final ([008](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540/008-phase-c-final.svg)): pause (`p`) / reset (`r`, `R`) / new-game (`n`) — game recovered cleanly.

No blockers/majors/minors/nits surfaced under the rule-based driver. Next
pass with a smarter (LLM-backed) driver might find gameplay-feel issues the
pilot can't articulate, but the core engine, menu loop, pause/reset, and
score HUD are all healthy on this build.

## Coverage

- Driver backend: `pilot`
- Keys pressed: 277 (unique: 24)
- State samples: 41 (unique: 11)
- Score samples: 41
- Phase durations (s): A=227.8, B=238.3, C=48.0
- Snapshots: [`reports/snaps/tetris-tui-20260423-091540/`](/home/brian/AI/projects/tui-dogfood/reports/snaps/tetris-tui-20260423-091540)
  (8 SVGs: 5 phase-A, 2 phase-B, 1 phase-C)
- Raw JSON: [`reports/tetris-tui-20260423-091540.json`](/home/brian/AI/projects/tui-dogfood/reports/tetris-tui-20260423-091540.json)
