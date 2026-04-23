"""Pure-Python Terminal-Blocks (Tetris-family) engine.

Mirrors the shape of a SWIG-bound native engine — one class, a `tick()`
step, a `state()` snapshot, `action(name)` verb dispatch — so the rest
of the TUI looks like every other tui-game-build project. No native
code required (see DECISIONS.md §1).

Rules implemented:

    * 10×20 visible matrix + 2 hidden buffer rows (total internal 10×22).
    * 7 tetrominoes (I/O/T/S/Z/J/L), SRS rotation with wall-kick table.
    * 7-bag randomizer (Random Generator).
    * Next-queue (5 upcoming) + single-slot hold with once-per-piece lock.
    * Gravity curve via Tetris-Worlds formula on a float accumulator.
    * Soft drop (20x gravity, 1 pt/cell), hard drop (instant, 2 pt/cell).
    * Lock delay with move-reset infinity (15 resets max).
    * Line clears: single/double/triple/tetris, scoring x level.
    * Game over on spawn-blocked.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Iterator, Literal

from . import pieces as _p


# ---------- constants ----------------------------------------------------

MATRIX_W = 10
VISIBLE_H = 20
BUFFER_H = 2
MATRIX_H = VISIBLE_H + BUFFER_H   # 22 internal rows; render rows 2..21

NEXT_QUEUE_LEN = 5

# Lock-delay / infinity caps — Guideline values.
LOCK_DELAY_S = 0.5
LOCK_MOVE_RESETS = 15

# Soft-drop multiplier — 20x of gravity per Guideline, but also never
# slower than "1 row per tick" to keep the key responsive at low levels.
SOFT_DROP_MULT = 20.0

# Scoring table (base points, multiplied by (level) at clear time).
LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}
SOFT_DROP_POINTS_PER_CELL = 1
HARD_DROP_POINTS_PER_CELL = 2

LINES_PER_LEVEL = 10
MAX_LEVEL = 20


Direction = Literal["left", "right"]
RotDir = Literal["cw", "ccw"]


# ---------- small dataclasses -------------------------------------------

@dataclass
class ActivePiece:
    """The piece currently under player control."""
    piece: str         # one of "I", "O", "T", "S", "Z", "J", "L"
    x: int             # origin column in the 10x22 matrix
    y: int             # origin row
    rotation: int = 0  # 0..3


@dataclass
class LineClearEvent:
    """Emitted by `tick()` / `action()` when a lock causes line clears.

    Consumed by the renderer (for the flash animation) and the sounds
    module (to pick a clip). Collect `pop_events()` once per render
    frame — the list is auto-cleared after read.
    """
    rows: list[int]              # matrix row indices cleared (inclusive)
    count: int                   # len(rows) convenience
    points: int                  # score added for this clear (x level)
    piece: str                   # what piece caused it
    t_spin: bool = False         # reserved for future T-spin detection


# ---------- gravity curve ------------------------------------------------

def gravity_frames(level: int) -> float:
    """Frames-per-row at the given level (Tetris Worlds formula).

    At level 1 this is 60 frames/row (~1 row per second at 60 fps).
    Goes to sub-frame at level ~16 — we clamp so we never divide by
    zero, and levels above MAX_LEVEL are treated as effectively-20G.
    """
    lvl = max(1, min(MAX_LEVEL, level))
    f = (0.8 - (lvl - 1) * 0.007) ** (lvl - 1) * 60.0
    return max(f, 0.05)   # floor: 0.05 frames/row == 20G-ish


# ---------- Game ---------------------------------------------------------

class Game:
    """Full game state. All mutations go through `action(name)` or
    `tick(dt)`.

    `action()` verbs:
        "left", "right"         — horizontal move (rejected on collision)
        "soft_drop"             — one row down + 1 point; resets lock timer
        "hard_drop"             — slam to landing, lock immediately
        "rotate_cw"             — rotate clockwise (SRS + kicks)
        "rotate_ccw"            — rotate counter-clockwise (SRS + kicks)
        "hold"                  — stash current piece (once per lock)
    """

    def __init__(self, *, start_level: int = 1,
                 rng: random.Random | None = None,
                 seed: int | None = None) -> None:
        if rng is not None:
            self.rng = rng
        elif seed is not None:
            self.rng = random.Random(seed)
        else:
            self.rng = random.Random()

        # Matrix: grid[y][x], 0 = empty, else stores piece letter.
        # Stored as single characters for cheap serialization; the
        # renderer maps letters → colors via pieces/colors module.
        self.grid: list[list[str]] = [
            ["" for _ in range(MATRIX_W)] for _ in range(MATRIX_H)
        ]

        # Piece queue — keep always >= NEXT_QUEUE_LEN + 1 entries so we
        # can peek at NEXT_QUEUE_LEN even with one pulled as active.
        self._bag: list[str] = []
        self._queue: list[str] = []
        self._refill_queue()

        # Active piece — pulled from queue.
        self.active: ActivePiece | None = None
        self.hold: str | None = None
        self._hold_used_this_turn = False

        # Gravity state.
        self.level = max(1, start_level)
        self.start_level = self.level
        self._gravity_accum = 0.0
        self._soft_dropping = False

        # Lock delay state.
        self._on_ground = False
        self._lock_timer = 0.0
        self._lock_moves = 0
        self._last_rotation_kicked = False  # hook for T-spin scoring

        # Stats.
        self.score = 0
        self.lines = 0
        self.moves_count = 0
        self.pieces_locked = 0
        self.start_time = time.monotonic()
        # Back-to-back counter — incremented on "hard" clears (tetris /
        # future T-spins); resets on a non-hard line clear.
        self._b2b = False

        # State flags.
        self.game_over = False
        self.paused = False

        # Event queue — drained by the renderer / sounds after each tick.
        self._events: list[LineClearEvent] = []
        self._lock_events: list[dict] = []  # {"piece":..., "tspin":..., "lines":0}

        # Seed the first active piece.
        self._spawn_next_piece()

    # ---- piece queue / bag ---------------------------------------------

    def _refill_queue(self) -> None:
        """Ensure the queue has enough entries for next-queue inspection."""
        while len(self._queue) < NEXT_QUEUE_LEN + 1:
            if not self._bag:
                self._bag = list(_p.PIECES)
                self.rng.shuffle(self._bag)
            self._queue.append(self._bag.pop(0))

    def _pop_next(self) -> str:
        self._refill_queue()
        return self._queue.pop(0)

    def peek_queue(self) -> list[str]:
        """Next NEXT_QUEUE_LEN pieces (not consuming)."""
        self._refill_queue()
        return self._queue[:NEXT_QUEUE_LEN]

    # ---- spawning / piece lifecycle ------------------------------------

    def _spawn_piece(self, piece: str) -> bool:
        """Place a new active piece in the spawn position. Returns False
        if the spawn is blocked (game-over condition)."""
        ox, oy = _p.spawn_origin(piece, MATRIX_W)
        candidate = ActivePiece(piece=piece, x=ox, y=oy, rotation=0)
        if self._collides(candidate):
            # Block-out: piece cannot spawn at all.
            self.active = candidate
            self.game_over = True
            return False
        self.active = candidate
        self._on_ground = False
        self._lock_timer = 0.0
        self._lock_moves = 0
        self._hold_used_this_turn = False
        self._last_rotation_kicked = False
        # Lock-out check: if the spawn position overlaps nothing but sits
        # entirely inside the buffer (y < BUFFER_H) after a soft landing,
        # we'll catch it at lock time.
        return True

    def _spawn_next_piece(self) -> bool:
        return self._spawn_piece(self._pop_next())

    # ---- collision / helpers ------------------------------------------

    def _cells_for(self, ap: ActivePiece) -> list[tuple[int, int]]:
        """Absolute matrix cells covered by a hypothetical piece."""
        offsets = _p.shape_cells(ap.piece, ap.rotation)
        return [(ap.x + dx, ap.y + dy) for (dx, dy) in offsets]

    def _collides(self, ap: ActivePiece) -> bool:
        for (x, y) in self._cells_for(ap):
            if x < 0 or x >= MATRIX_W:
                return True
            if y < 0:
                # allow negative y (piece poking above spawn buffer) —
                # the top-2 buffer rows exist for exactly that.
                return True
            if y >= MATRIX_H:
                return True
            if self.grid[y][x]:
                return True
        return False

    def _touching_ground(self, ap: ActivePiece) -> bool:
        """Would this piece collide if it moved one row down?"""
        test = ActivePiece(piece=ap.piece, x=ap.x, y=ap.y + 1,
                           rotation=ap.rotation)
        return self._collides(test)

    # ---- actions -------------------------------------------------------

    def action(self, name: str) -> bool:
        """Apply a player action. Returns True if the action had effect.

        No-op if game_over or paused (except `pause` / `resume` which are
        handled by the caller, not through action())."""
        if self.game_over or self.paused or self.active is None:
            return False
        fn = getattr(self, f"_a_{name}", None)
        if fn is None:
            return False
        return bool(fn())

    # ---- action handlers ----------------------------------------------

    def _a_left(self) -> bool:
        return self._translate(-1)

    def _a_right(self) -> bool:
        return self._translate(1)

    def _a_soft_drop(self) -> bool:
        """Step down one row. Returns True if it moved."""
        assert self.active is not None
        test = ActivePiece(piece=self.active.piece, x=self.active.x,
                           y=self.active.y + 1, rotation=self.active.rotation)
        if self._collides(test):
            # Already on-ground. Soft-drop still signals intent but doesn't
            # move — update lock state.
            self._on_ground = True
            return False
        self.active = test
        self.score += SOFT_DROP_POINTS_PER_CELL
        self._refresh_ground_state(moved=False)
        return True

    def _a_hard_drop(self) -> bool:
        """Drop to landing + lock immediately."""
        assert self.active is not None
        dropped = 0
        while True:
            test = ActivePiece(piece=self.active.piece, x=self.active.x,
                               y=self.active.y + 1,
                               rotation=self.active.rotation)
            if self._collides(test):
                break
            self.active = test
            dropped += 1
        self.score += dropped * HARD_DROP_POINTS_PER_CELL
        self._lock_piece()
        return True

    def _a_rotate_cw(self) -> bool:
        return self._rotate(+1)

    def _a_rotate_ccw(self) -> bool:
        return self._rotate(-1)

    def _a_hold(self) -> bool:
        """Swap active piece with the hold slot. Once per lock."""
        if self._hold_used_this_turn or self.active is None:
            return False
        current = self.active.piece
        if self.hold is None:
            self.hold = current
            ok = self._spawn_next_piece()
        else:
            swapped = self.hold
            self.hold = current
            ok = self._spawn_piece(swapped)
        self._hold_used_this_turn = True
        return ok

    # ---- internal move/rotate helpers ---------------------------------

    def _translate(self, dx: int) -> bool:
        assert self.active is not None
        test = ActivePiece(piece=self.active.piece,
                           x=self.active.x + dx,
                           y=self.active.y,
                           rotation=self.active.rotation)
        if self._collides(test):
            return False
        self.active = test
        self._refresh_ground_state(moved=True)
        return True

    def _rotate(self, direction: int) -> bool:
        """SRS rotation with wall kicks. direction=+1 CW, -1 CCW."""
        assert self.active is not None
        ap = self.active
        from_r = ap.rotation % 4
        to_r = (ap.rotation + direction) % 4
        kicks = _p.kicks_for(ap.piece, from_r, to_r)
        for (kx, ky) in kicks:
            test = ActivePiece(piece=ap.piece,
                               x=ap.x + kx,
                               y=ap.y + ky,
                               rotation=to_r)
            if not self._collides(test):
                self.active = test
                self._last_rotation_kicked = (kx, ky) != (0, 0)
                self._refresh_ground_state(moved=True)
                return True
        return False

    def _refresh_ground_state(self, *, moved: bool) -> None:
        """After a translate/rotate/soft-drop that moved the piece, see
        if we're now on-ground (piece can't fall further). If a move or
        rotate happened while on-ground, reset the lock timer up to the
        infinity cap."""
        assert self.active is not None
        on = self._touching_ground(self.active)
        if on:
            if not self._on_ground:
                # Just landed. Start the lock timer fresh.
                self._on_ground = True
                self._lock_timer = 0.0
                self._lock_moves = 0
            elif moved:
                # Already grounded but player moved — reset timer if we
                # haven't exceeded the infinity cap.
                if self._lock_moves < LOCK_MOVE_RESETS:
                    self._lock_timer = 0.0
                    self._lock_moves += 1
        else:
            # Lifted off ground (rotation kick upward, or new row below).
            self._on_ground = False
            self._lock_timer = 0.0
            # Note: we do NOT reset _lock_moves here — player "landed,
            # kicked up, landed again" is still bounded by the same cap.

    # ---- tick / gravity ------------------------------------------------

    def tick(self, dt: float) -> list[LineClearEvent]:
        """Advance gravity + lock timer by `dt` seconds. Returns any line
        clear events that occurred during this tick (also queued on
        `self._events`)."""
        if self.game_over or self.paused or self.active is None:
            return []

        events_before = len(self._events)

        # If the piece is already resting on ground (e.g. spawn-landed),
        # keep the lock timer ticking even if we haven't done a gravity
        # step this tick. The test harness relies on this for low-latency
        # lock-delay scenarios.
        if not self._on_ground and self._touching_ground(self.active):
            self._on_ground = True
            self._lock_timer = 0.0

        # Gravity step — add 1 row per `gravity_frames(level) / 60` seconds.
        # Soft drop multiplies the fall rate (but we also handle the
        # per-keystroke soft-drop in _a_soft_drop for direct player feel).
        frames_per_row = gravity_frames(self.level)
        rate = 60.0 / frames_per_row     # rows per second at this level
        if self._soft_dropping:
            rate *= SOFT_DROP_MULT
        self._gravity_accum += rate * dt

        while self._gravity_accum >= 1.0 and not self.game_over:
            self._gravity_accum -= 1.0
            moved = self._gravity_step()
            if not moved:
                # Piece is grounded — let lock timer run.
                break

        # Lock delay: if on-ground, accumulate lock time; past threshold
        # → lock.
        if self._on_ground and self.active is not None:
            self._lock_timer += dt
            if self._lock_timer >= LOCK_DELAY_S:
                self._lock_piece()

        return self._events[events_before:]

    def _gravity_step(self) -> bool:
        """Try to drop the active piece one row from gravity. Returns
        True if moved, False if blocked (now on-ground)."""
        assert self.active is not None
        test = ActivePiece(piece=self.active.piece, x=self.active.x,
                           y=self.active.y + 1,
                           rotation=self.active.rotation)
        if self._collides(test):
            self._on_ground = True
            return False
        self.active = test
        # Soft drop bonus — if the drop came from held soft-drop key,
        # score the point.
        if self._soft_dropping:
            self.score += SOFT_DROP_POINTS_PER_CELL
        # Falling naturally → reset any lock timer state.
        self._on_ground = False
        self._lock_timer = 0.0
        return True

    # ---- locking + line clears ----------------------------------------

    def _lock_piece(self) -> None:
        """Imprint the active piece into the grid, check for line clears,
        spawn the next piece. Game-over if piece locked entirely in the
        buffer rows (lock-out) or if next spawn collides (block-out)."""
        assert self.active is not None
        ap = self.active
        cells = self._cells_for(ap)
        # Lock-out: piece locked ENTIRELY above the visible area.
        if all(y < BUFFER_H for (_x, y) in cells):
            self.game_over = True
            return
        for (x, y) in cells:
            if 0 <= y < MATRIX_H and 0 <= x < MATRIX_W:
                self.grid[y][x] = ap.piece

        # Line clear scan.
        cleared_rows: list[int] = []
        for y in range(MATRIX_H):
            if all(self.grid[y][x] for x in range(MATRIX_W)):
                cleared_rows.append(y)
        if cleared_rows:
            self._collapse_rows(cleared_rows)
            base = LINE_SCORES.get(len(cleared_rows), 0)
            points = base * self.level
            # Back-to-back bonus: consecutive tetrises (or T-spins, later)
            # get a 1.5x multiplier.
            is_hard = len(cleared_rows) == 4  # tetris counts as hard
            if is_hard and self._b2b:
                points = int(points * 1.5)
            self._b2b = is_hard
            self.score += points
            self.lines += len(cleared_rows)
            self._maybe_level_up()
            self._events.append(LineClearEvent(
                rows=cleared_rows,
                count=len(cleared_rows),
                points=points,
                piece=ap.piece,
            ))
        else:
            self._b2b = self._b2b  # no change unless hard-clear just above

        self._lock_events.append({
            "piece": ap.piece,
            "tspin": False,
            "lines": len(cleared_rows),
        })
        self.pieces_locked += 1
        self._spawn_next_piece()

    def _collapse_rows(self, rows: list[int]) -> None:
        """Remove cleared rows, prepend empty rows on top. Rows are given
        as matrix-absolute indices."""
        for y in rows:
            self.grid.pop(y)
            self.grid.insert(0, ["" for _ in range(MATRIX_W)])

    def _maybe_level_up(self) -> None:
        """Level = 1 + lines//LINES_PER_LEVEL + (start_level - 1). Never
        go below start_level."""
        new_level = max(self.start_level,
                        1 + self.lines // LINES_PER_LEVEL
                        + (self.start_level - 1))
        if new_level != self.level:
            self.level = min(MAX_LEVEL, new_level)

    # ---- ghost piece ---------------------------------------------------

    def ghost_position(self) -> tuple[int, int] | None:
        """Compute the row the active piece would land at if hard-dropped
        right now. Returns (x, y) of the ghost origin, or None if no
        active piece."""
        if self.active is None:
            return None
        ap = self.active
        y = ap.y
        while True:
            test = ActivePiece(piece=ap.piece, x=ap.x, y=y + 1,
                               rotation=ap.rotation)
            if self._collides(test):
                break
            y += 1
        return (ap.x, y)

    # ---- soft-drop latch ----------------------------------------------

    def set_soft_drop(self, on: bool) -> None:
        """Called by the UI on key-down / key-up of the soft-drop key.
        In practice most TUIs don't get key-up events, so the app ticks
        this off after each press — either works."""
        self._soft_dropping = bool(on)

    # ---- pause ---------------------------------------------------------

    def toggle_pause(self) -> bool:
        """Flip pause state. Returns new pause state. No-op if game_over."""
        if self.game_over:
            return False
        self.paused = not self.paused
        return self.paused

    # ---- introspection -------------------------------------------------

    def cells(self) -> Iterator[tuple[int, int, str]]:
        """Iterate (x, y, piece_letter) for all NON-EMPTY matrix cells,
        EXCLUDING the active piece. The active piece is overlaid by the
        renderer separately so animations work cleanly."""
        for y in range(MATRIX_H):
            row = self.grid[y]
            for x in range(MATRIX_W):
                if row[x]:
                    yield x, y, row[x]

    def active_cells(self) -> list[tuple[int, int, str]]:
        """Matrix cells the active piece currently occupies (excluding
        anything off-grid)."""
        if self.active is None:
            return []
        out: list[tuple[int, int, str]] = []
        for (x, y) in self._cells_for(self.active):
            if 0 <= x < MATRIX_W and 0 <= y < MATRIX_H:
                out.append((x, y, self.active.piece))
        return out

    def ghost_cells(self) -> list[tuple[int, int, str]]:
        """Ghost-piece cells for the current active piece's landing row."""
        if self.active is None:
            return []
        pos = self.ghost_position()
        if pos is None:
            return []
        gx, gy = pos
        ap = self.active
        offsets = _p.shape_cells(ap.piece, ap.rotation)
        out: list[tuple[int, int, str]] = []
        for (dx, dy) in offsets:
            x, y = gx + dx, gy + dy
            if 0 <= x < MATRIX_W and 0 <= y < MATRIX_H:
                out.append((x, y, ap.piece))
        return out

    def state(self) -> dict:
        """Snapshot for panels + QA + optional agent API."""
        elapsed = time.monotonic() - self.start_time
        return {
            "matrix_w": MATRIX_W,
            "matrix_h": MATRIX_H,
            "visible_h": VISIBLE_H,
            "buffer_h": BUFFER_H,
            "score": self.score,
            "lines": self.lines,
            "level": self.level,
            "pieces_locked": self.pieces_locked,
            "moves_count": self.moves_count,
            "active": (
                {"piece": self.active.piece,
                 "x": self.active.x, "y": self.active.y,
                 "rotation": self.active.rotation}
                if self.active else None
            ),
            "hold": self.hold,
            "hold_used": self._hold_used_this_turn,
            "next": self.peek_queue(),
            "game_over": self.game_over,
            "paused": self.paused,
            "elapsed": elapsed,
            "on_ground": self._on_ground,
            "b2b": self._b2b,
        }

    # ---- serialisation -------------------------------------------------

    def to_dict(self) -> dict:
        """Minimal JSON-serialisable snapshot. Active piece is NOT saved —
        on resume we treat the piece as not-yet-placed and spawn fresh
        from the queue."""
        return {
            "grid": [list(row) for row in self.grid],
            "queue": list(self._queue),
            "bag": list(self._bag),
            "hold": self.hold,
            "score": self.score,
            "lines": self.lines,
            "level": self.level,
            "start_level": self.start_level,
            "pieces_locked": self.pieces_locked,
            "b2b": self._b2b,
        }

    @classmethod
    def from_dict(cls, data: dict,
                  rng: random.Random | None = None) -> "Game":
        g = cls(start_level=int(data.get("start_level", 1)), rng=rng)
        # Overwrite the fresh-game state.
        grid = data.get("grid")
        if grid and len(grid) == MATRIX_H:
            g.grid = [list(row) for row in grid]
        g._queue = list(data.get("queue", []))
        g._bag = list(data.get("bag", []))
        g.hold = data.get("hold")
        g.score = int(data.get("score", 0))
        g.lines = int(data.get("lines", 0))
        g.level = int(data.get("level", 1))
        g.pieces_locked = int(data.get("pieces_locked", 0))
        g._b2b = bool(data.get("b2b", False))
        g._refill_queue()
        # Re-spawn the active piece from the (possibly restored) queue.
        g._spawn_next_piece()
        return g

    # ---- agent/test convenience ---------------------------------------

    def pop_events(self) -> list[LineClearEvent]:
        """Drain pending line-clear events. The renderer calls this once
        per frame so it can trigger flash animations."""
        out = self._events
        self._events = []
        return out

    def pop_lock_events(self) -> list[dict]:
        out = self._lock_events
        self._lock_events = []
        return out
