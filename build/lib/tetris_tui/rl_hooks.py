"""RL exposure hooks for tetromino-tui.

Headless adapter — bypasses Textual entirely. Wraps engine.Game to
expose the tui-rl env hook surface:

    game_state_vector() -> np.ndarray    (flat float32)
    game_reward()        -> float         (score delta + shaping)
    is_terminal()        -> bool
    reset_game()         -> None

State vector layout (len 233):
    [0 : 200]    visible 10x20 grid, 1.0 if filled, 0.0 empty
    [200 : 207]  active piece one-hot (I,O,T,S,Z,J,L)
    [207 : 210]  active x/10, active y/22, rotation/4
    [210 : 217]  hold piece one-hot (all 0 if None)
    [217 : 222]  next-queue (5 pieces) index/7
    [222]        score / 10000
    [223]        level / 20
    [224]        lines / 200
    [225]        pieces_locked / 500
    [226]        game_over flag
    [227]        paused flag
    [228]        on_ground flag
    [229]        b2b flag
    [230]        hold_used flag
    [231]        gravity_accum
    [232]        lock_timer / LOCK_DELAY_S

Actions: Discrete(7)
    0 left  1 right  2 soft_drop  3 hard_drop
    4 rotate_cw  5 rotate_ccw  6 hold

Reward:
    +score_delta / 100.0   (roughly: single=1.0, tetris=8.0 at level 1)
    -1.0 if game_over happened this step
    -0.005 per tick (time penalty)
"""

from __future__ import annotations

import numpy as np

from . import pieces as _p
from .engine import (
    BUFFER_H,
    Game,
    LOCK_DELAY_S,
    MATRIX_H,
    MATRIX_W,
    VISIBLE_H,
)


PIECES_ORDER = ("I", "O", "T", "S", "Z", "J", "L")
PIECE_INDEX = {p: i for i, p in enumerate(PIECES_ORDER)}

STATE_DIM = VISIBLE_H * MATRIX_W + 7 + 3 + 7 + 5 + 12   # 200+7+3+7+5+12 = 234
# Breakdown check:  200 grid + 7 active + 3 pos + 7 hold + 5 next + 12 scalars = 234


def state_vector(game: Game) -> np.ndarray:
    out = np.zeros(STATE_DIM, dtype=np.float32)
    # Visible grid (skip BUFFER_H top rows).
    idx = 0
    for y in range(BUFFER_H, BUFFER_H + VISIBLE_H):
        row = game.grid[y]
        for x in range(MATRIX_W):
            out[idx] = 1.0 if row[x] else 0.0
            idx += 1
    # Active piece.
    if game.active is not None:
        ap = game.active
        pi = PIECE_INDEX.get(ap.piece)
        if pi is not None:
            out[200 + pi] = 1.0
        out[207] = ap.x / float(MATRIX_W)
        out[208] = ap.y / float(MATRIX_H)
        out[209] = (ap.rotation % 4) / 4.0
    # Hold piece.
    if game.hold is not None:
        hi = PIECE_INDEX.get(game.hold)
        if hi is not None:
            out[210 + hi] = 1.0
    # Next queue (up to 5).
    q = game.peek_queue()
    for i, pc in enumerate(q[:5]):
        out[217 + i] = PIECE_INDEX.get(pc, 0) / 7.0
    # Scalars.
    out[222] = game.score / 10000.0
    out[223] = game.level / 20.0
    out[224] = game.lines / 200.0
    out[225] = game.pieces_locked / 500.0
    out[226] = 1.0 if game.game_over else 0.0
    out[227] = 1.0 if game.paused else 0.0
    out[228] = 1.0 if game._on_ground else 0.0
    out[229] = 1.0 if game._b2b else 0.0
    out[230] = 1.0 if game._hold_used_this_turn else 0.0
    out[231] = min(1.0, game._gravity_accum)
    out[232] = min(1.0, game._lock_timer / max(1e-6, LOCK_DELAY_S))
    # out[233] reserved/padding — STATE_DIM is 234 total
    return out


def state_vector_len() -> int:
    return STATE_DIM


ACTIONS = ("left", "right", "soft_drop", "hard_drop",
           "rotate_cw", "rotate_ccw", "hold")


def apply_action(game: Game, action_idx: int) -> bool:
    name = ACTIONS[int(action_idx) % len(ACTIONS)]
    return game.action(name)


def compute_reward(prev_score: int, prev_game_over: bool,
                   game: Game) -> float:
    score_delta = game.score - prev_score
    died = (not prev_game_over) and game.game_over
    return float(score_delta / 100.0
                 + (-1.0 if died else 0.0)
                 - 0.005)


def is_terminal(game: Game) -> bool:
    return bool(game.game_over)
