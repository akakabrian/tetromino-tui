"""Performance baseline for tetromino-tui.

Tetris is a small matrix (10×20) so rendering is never going to be the
bottleneck, but we still want a baseline so a future "polish" commit
that accidentally regresses the hot path is obvious.

Hot paths:
    * engine.tick(dt) — gravity + line-clear scan
    * engine.action("hard_drop") — collision scan + lock + clear
    * MatrixView.render_line(y) × 20 rows — the per-frame cost
"""

from __future__ import annotations

import os
import statistics as stats
import sys
import time

import tempfile as _tempfile
os.environ.setdefault("XDG_DATA_HOME",
                      _tempfile.mkdtemp(prefix="tetris-perf-"))

from tetromino_tui.engine import Game, ActivePiece, MATRIX_H, MATRIX_W  # noqa: E402


def bench(name, fn, n=1000):
    samples = []
    # Warm up.
    for _ in range(min(50, n // 10)):
        fn()
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)   # μs
    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[int(len(samples) * 0.95)]
    mean = stats.fmean(samples)
    print(f"  {name:<40} p50 {p50:7.2f} μs   p95 {p95:7.2f} μs   "
          f"mean {mean:7.2f} μs   n={n}")
    return p50


def bench_tick():
    g = Game(seed=1)

    def _go():
        g.tick(0.016)

    bench("Game.tick(16ms)", _go, n=5000)


def bench_hard_drop():
    def _go():
        g = Game(seed=1)
        g.action("hard_drop")
    bench("Game.hard_drop (from fresh)", _go, n=2000)


def bench_render_line():
    """Render all 20 visible rows of the matrix."""
    # Need an App context to construct MatrixView. Cheap alternative:
    # render the matrix rows via the engine directly — i.e. build the
    # per-row "row_cells / row_kind" arrays which is what dominates
    # render_line cost anyway.
    g = Game(seed=2)
    # Lock a bunch of pieces so the grid is non-trivial.
    for _ in range(10):
        g.action("hard_drop")

    def _go():
        for y in range(MATRIX_H):
            row_cells = ["" for _ in range(MATRIX_W)]
            for x, letter in enumerate(g.grid[y]):
                if letter:
                    row_cells[x] = letter
            for (ax, ay, letter) in g.active_cells():
                if ay == y:
                    row_cells[ax] = letter
            _ = row_cells  # touch

    bench("engine row-build × 22 rows", _go, n=2000)


def bench_collision():
    g = Game(seed=3)

    def _go():
        ap = ActivePiece(piece="T", x=3, y=5, rotation=0)
        g._collides(ap)

    bench("Game._collides (4 cells)", _go, n=20000)


def bench_rotate_cw():
    def _go():
        g = Game(seed=4)
        g.active = ActivePiece(piece="T", x=3, y=10, rotation=0)
        g.action("rotate_cw")
    bench("Game.rotate_cw", _go, n=5000)


def bench_line_clear_scan():
    """Scan the grid for full rows — runs on every lock."""
    g = Game(seed=5)
    # Fill bottom 4 rows entirely.
    for y in range(MATRIX_H - 4, MATRIX_H):
        for x in range(MATRIX_W):
            g.grid[y][x] = "L"

    def _go():
        cleared = []
        for y in range(MATRIX_H):
            if all(g.grid[y][x] for x in range(MATRIX_W)):
                cleared.append(y)
        _ = cleared

    bench("line-clear scan (full grid)", _go, n=10000)


def main(argv):
    print("tetromino-tui perf baseline")
    print("-" * 72)
    bench_tick()
    bench_hard_drop()
    bench_render_line()
    bench_collision()
    bench_rotate_cw()
    bench_line_clear_scan()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
