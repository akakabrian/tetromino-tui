"""Rules text for tetromino-tui."""

RULES_TEXT = '''
TETROMINO
=========

Clear horizontal lines by filling rows with falling blocks.

Object
------
Score as many points as possible before the stack reaches the top.

Rules
-----
Seven tetromino shapes (I, O, T, S, Z, L, J) fall from the top of the
playfield. Rotate and move them to fill complete rows. A full row
clears and scores points.

Clearing multiple lines at once scores more: 1 line = 100 × level,
2 lines = 300, 3 lines = 500, 4 lines (a "tetris") = 800 × level.

Every 10 lines cleared advances the level, speeding up the drop rate.

Game ends when a new piece cannot spawn because the stack has filled
the top of the playfield.

Controls summary
----------------
Move:   ← →
Drop:   ↓ (soft) / Space (hard)
Rotate: z / x (ccw / cw)
Hold:   c
Pause:  p
'''
