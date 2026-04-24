"""Tetromino shapes + SRS (Super Rotation System) rotation tables.

Clean-room implementation from the Tetris Guideline / SRS article on
the Tetris Wiki — no Tetris-Company assets are reused. The specific
offset tables below are the *mathematical* SRS kick tables, which are
de facto standard across every guideline-compliant clone.

Seven pieces, each with four rotation states:

    R0 — spawn orientation
    R  — rotated 90° clockwise from spawn
    R2 — 180° from spawn
    R' — rotated 90° counter-clockwise from spawn

Each rotation is a 4-tuple of `(x, y)` offsets from a piece-local
origin. The origin is placed so all four rotations tile into the same
4×4 bounding box (classic SRS layout).

SRS WALL KICKS
--------------

When rotation collides with the matrix, we try up to 5 *kick offsets*
from a kick table indexed by (from_rotation, to_rotation). If all five
fail, the rotation is rejected.

Two kick tables:

    * JLSTZ_KICKS — shared by J, L, S, T, Z.
    * I_KICKS     — the I piece rotates around a different center.

The O piece has no effective rotation; we still accept the input as a
no-op so the state machine stays clean.
"""

from __future__ import annotations

from typing import Iterable

Cell = tuple[int, int]  # (x, y) — y grows DOWN (screen coords)
Shape = tuple[Cell, Cell, Cell, Cell]   # four cells per tetromino
Rotations = tuple[Shape, Shape, Shape, Shape]  # R0, R, R2, R'

PIECES: tuple[str, ...] = ("I", "O", "T", "S", "Z", "J", "L")


# ---------------------------------------------------------------------
# SHAPE TABLES — cells in each rotation, y grows DOWN.
# ---------------------------------------------------------------------
#
# Coordinates chosen so every rotation fits in a 4x4 bounding box with
# the SRS rotation center at (1.5, 1.5) for I, (1, 1) for the others.
# Reference: tetris.wiki/Super_Rotation_System

# I-piece — rotates in a 4x4 box.
#   R0:  . . . .       R:   . . X .       R2:  . . . .       R':  . X . .
#        X X X X            . . X .            . . . .            . X . .
#        . . . .            . . X .            X X X X            . X . .
#        . . . .            . . X .            . . . .            . X . .
I_R0 = ((0, 1), (1, 1), (2, 1), (3, 1))
I_R1 = ((2, 0), (2, 1), (2, 2), (2, 3))
I_R2 = ((0, 2), (1, 2), (2, 2), (3, 2))
I_R3 = ((1, 0), (1, 1), (1, 2), (1, 3))

# O-piece — 2x2 square, does not actually rotate.
O_SHAPE = ((1, 0), (2, 0), (1, 1), (2, 1))

# T-piece
#   R0:  . X .       R:   . X .       R2:  . . .       R':  . X .
#        X X X            . X X            X X X            X X .
#        . . .            . X .            . X .            . X .
T_R0 = ((1, 0), (0, 1), (1, 1), (2, 1))
T_R1 = ((1, 0), (1, 1), (2, 1), (1, 2))
T_R2 = ((0, 1), (1, 1), (2, 1), (1, 2))
T_R3 = ((1, 0), (0, 1), (1, 1), (1, 2))

# S-piece
S_R0 = ((1, 0), (2, 0), (0, 1), (1, 1))
S_R1 = ((1, 0), (1, 1), (2, 1), (2, 2))
S_R2 = ((1, 1), (2, 1), (0, 2), (1, 2))
S_R3 = ((0, 0), (0, 1), (1, 1), (1, 2))

# Z-piece
Z_R0 = ((0, 0), (1, 0), (1, 1), (2, 1))
Z_R1 = ((2, 0), (1, 1), (2, 1), (1, 2))
Z_R2 = ((0, 1), (1, 1), (1, 2), (2, 2))
Z_R3 = ((1, 0), (0, 1), (1, 1), (0, 2))

# J-piece
J_R0 = ((0, 0), (0, 1), (1, 1), (2, 1))
J_R1 = ((1, 0), (2, 0), (1, 1), (1, 2))
J_R2 = ((0, 1), (1, 1), (2, 1), (2, 2))
J_R3 = ((1, 0), (1, 1), (0, 2), (1, 2))

# L-piece
L_R0 = ((2, 0), (0, 1), (1, 1), (2, 1))
L_R1 = ((1, 0), (1, 1), (1, 2), (2, 2))
L_R2 = ((0, 1), (1, 1), (2, 1), (0, 2))
L_R3 = ((0, 0), (1, 0), (1, 1), (1, 2))


SHAPES: dict[str, Rotations] = {
    "I": (I_R0, I_R1, I_R2, I_R3),
    "O": (O_SHAPE, O_SHAPE, O_SHAPE, O_SHAPE),
    "T": (T_R0, T_R1, T_R2, T_R3),
    "S": (S_R0, S_R1, S_R2, S_R3),
    "Z": (Z_R0, Z_R1, Z_R2, Z_R3),
    "J": (J_R0, J_R1, J_R2, J_R3),
    "L": (L_R0, L_R1, L_R2, L_R3),
}


# ---------------------------------------------------------------------
# SRS WALL KICK TABLES
# ---------------------------------------------------------------------
#
# Kicks are stored as `(dx, dy)` offsets. Note that SRS publications
# give kicks with y growing UP; we invert y (negate) to match our
# screen-coord convention (y grows DOWN).
#
# Keys: (from_rotation, to_rotation) as 0/1/2/3 indices.
# The (R0 → R) and reverse kicks come from the standard SRS table.

def _invert_y(kicks: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Convert SRS spec kicks (y-up) to our y-down convention."""
    return tuple((x, -y) for (x, y) in kicks)


# JLSTZ kicks — shared across 5 pieces.
JLSTZ_KICKS: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {
    (0, 1): _invert_y([(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)]),
    (1, 0): _invert_y([(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)]),
    (1, 2): _invert_y([(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)]),
    (2, 1): _invert_y([(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)]),
    (2, 3): _invert_y([(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]),
    (3, 2): _invert_y([(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)]),
    (3, 0): _invert_y([(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)]),
    (0, 3): _invert_y([(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)]),
}

# I-piece kicks.
I_KICKS: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {
    (0, 1): _invert_y([(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)]),
    (1, 0): _invert_y([(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)]),
    (1, 2): _invert_y([(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)]),
    (2, 1): _invert_y([(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)]),
    (2, 3): _invert_y([(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)]),
    (3, 2): _invert_y([(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)]),
    (3, 0): _invert_y([(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)]),
    (0, 3): _invert_y([(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)]),
}


def kicks_for(piece: str, frm: int, to: int) -> tuple[tuple[int, int], ...]:
    """Return the SRS kick-offset sequence for a given piece + transition.
    O-piece returns a single zero-offset (no-op). Unknown transitions
    return a single zero-offset as a safety fallback."""
    if piece == "O":
        return ((0, 0),)
    table = I_KICKS if piece == "I" else JLSTZ_KICKS
    return table.get((frm, to), ((0, 0),))


# ---------------------------------------------------------------------
# Helpers for the game + renderer
# ---------------------------------------------------------------------

def shape_cells(piece: str, rotation: int) -> Shape:
    """Raw 4-cell tuple for a piece at the given rotation index (0..3).
    Offsets are piece-local; add `(origin_x, origin_y)` to get matrix
    coordinates."""
    return SHAPES[piece][rotation % 4]


def spawn_origin(piece: str, matrix_width: int) -> tuple[int, int]:
    """Where to place the piece's local origin when it spawns.

    All pieces spawn with their top row at matrix y=0 (the topmost
    hidden buffer row). Horizontal center: SRS rule is "center on the
    middle columns". For width=10 that's columns 3/4 — shift each piece
    so its bounding box lands there.
    """
    if piece == "I":
        # I-piece's 4x4 bounding box; origin at (left-3, top-0)
        # makes cells land at columns 3..6 in R0.
        return (3, 0)
    if piece == "O":
        # O's 4-cell at (1,0)/(2,0)/(1,1)/(2,1) — origin (3,0) → cols 4..5.
        return (3, 0)
    # JLSTZ-like pieces fit in a 3x3 bounding box with origin at (3, 0).
    return (3, 0)
