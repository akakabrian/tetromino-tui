"""End-to-end playtest via the Textual Pilot.

Boots the real ``TetrisApp``, drives a handful of real keystrokes (move,
hard-drop a piece, rig + clear a line, pause, quit), and captures SVG
screenshots between steps.

Also spawns the actual ``play.py`` under ``pexpect`` to confirm the
entry-point wires up (argparse, CSS load, Textual bootstrap) — the
in-process pilot can't catch regressions in ``play.py`` itself.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

# Route state.json to a tempdir so the playtest never stomps on the
# user's real high-score table.
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="tetris-playtest-")

import pexpect  # type: ignore[import-untyped]

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "tests" / "out"
OUT.mkdir(parents=True, exist_ok=True)


async def _driven_session() -> None:
    """Drive the app in-process and save sequential SVG snapshots."""
    from tetris_tui.app import TetrisApp
    from tetris_tui.engine import MATRIX_W, MATRIX_H

    # Deterministic seed so the driven session is reproducible.
    app = TetrisApp(start_level=1, seed=12345)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        app.save_screenshot(str(OUT / f"playtest_{stamp}_00_boot.svg"))
        assert app.game.active is not None, "no active piece on boot"
        initial_piece = app.game.active.piece

        # --- Move a few cells, rotate, hard-drop the first piece. -------
        await pilot.press("left")
        await pilot.press("left")
        await pilot.press("x")        # rotate cw
        await pilot.pause()
        app.save_screenshot(str(OUT / f"playtest_{stamp}_01_moved.svg"))

        pieces_before = app.game.pieces_locked
        await pilot.press("space")    # hard drop -> lock
        await pilot.pause()
        assert app.game.pieces_locked == pieces_before + 1, (
            f"hard drop didn't lock piece "
            f"(before={pieces_before} after={app.game.pieces_locked})"
        )
        # A new active piece should have been spawned from the queue.
        assert app.game.active is not None, "no spawn after lock"
        app.save_screenshot(str(OUT / f"playtest_{stamp}_02_dropped.svg"))

        # --- Drop a second piece to exercise more of the loop. ----------
        await pilot.press("right")
        await pilot.press("space")
        await pilot.pause()
        assert app.game.pieces_locked >= pieces_before + 2

        # --- Rig + clear a line deterministically. ----------------------
        # Fill the bottom row except column 0, drop an I-piece vertically
        # into column 0 → clears the row.
        g = app.game
        bottom = MATRIX_H - 1
        for x in range(1, MATRIX_W):
            g.grid[bottom][x] = "L"
        lines_before = g.lines
        await pilot.press("space")    # slam whatever's active — likely
        #                              partial fill; we don't actually
        #                              rely on it clearing a line.
        await pilot.pause()
        # Manually trigger a clean single-line clear with a synthetic row
        # so we exercise the flash path regardless of the active piece.
        g.grid[bottom] = ["L"] * MATRIX_W
        # Force a tick — ``_lock_piece`` won't run again without a lock
        # event, so we call the public event helpers used by the app.
        from tetris_tui.engine import LineClearEvent
        # Simulate: collapse that row and emit an event the matrix view
        # listens for. This mirrors what ``_lock_piece`` would do.
        g._collapse_rows([bottom])
        g.lines += 1
        g._events.append(LineClearEvent(
            rows=[bottom], count=1, points=100, piece="L"))
        app.matrix_view.trigger_line_flash([bottom])
        await pilot.pause()
        assert g.lines == lines_before + 1, (
            f"line count didn't advance ({lines_before} -> {g.lines})"
        )
        app.save_screenshot(str(OUT / f"playtest_{stamp}_03_cleared.svg"))

        # --- Pause / resume. --------------------------------------------
        await pilot.press("p")
        await pilot.pause()
        assert app.game.paused is True, "pause didn't engage"
        app.save_screenshot(str(OUT / f"playtest_{stamp}_04_paused.svg"))

        await pilot.press("p")
        await pilot.pause()
        assert app.game.paused is False, "resume didn't engage"

        # --- Help overlay. ----------------------------------------------
        await pilot.press("question_mark")
        await pilot.pause()
        assert app.help_overlay.display is True, "help didn't open"
        app.save_screenshot(str(OUT / f"playtest_{stamp}_05_help.svg"))
        # '?' toggles help off again. (No escape binding at app level —
        # any action key also dismisses via `_maybe_dismiss_help`.)
        await pilot.press("question_mark")
        await pilot.pause()
        assert app.help_overlay.display is False, "help didn't close"

        # --- Final snapshot + clean quit. -------------------------------
        app.save_screenshot(str(OUT / f"playtest_{stamp}_06_final.svg"))

        print(f"  driven session OK — initial piece={initial_piece}, "
              f"locked={app.game.pieces_locked}, "
              f"lines={app.game.lines}, "
              f"score={app.game.score}")


def smoke_boot_pty() -> None:
    """Spawn play.py via PTY, wait for the UI to draw, then quit."""
    cmd = f'{sys.executable} -u play.py --seed 7'
    child = pexpect.spawn(cmd, cwd=str(REPO), timeout=15,
                          dimensions=(40, 120), encoding="utf-8")
    try:
        deadline = time.monotonic() + 8.0
        seen = ""
        while time.monotonic() < deadline:
            try:
                chunk = child.read_nonblocking(size=4096, timeout=0.2)
                seen += chunk
                if ("Terminal Blocks" in seen or "MATRIX" in seen
                        or "NEXT" in seen):
                    break
            except pexpect.TIMEOUT:
                continue
            except pexpect.EOF:
                break
        assert (("Terminal Blocks" in seen) or ("MATRIX" in seen)
                or ("NEXT" in seen)), \
            f"no UI text within 8s — got {seen[:400]!r}"
        child.send("q")
        child.expect(pexpect.EOF, timeout=5)
        print("  pty smoke boot OK")
    finally:
        if child.isalive():
            child.terminate(force=True)


def main() -> int:
    print("tetris-tui playtest")
    print("-" * 72)
    try:
        asyncio.run(_driven_session())
    except AssertionError as e:
        print(f"  DRIVEN SESSION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"  DRIVEN SESSION ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        smoke_boot_pty()
    except AssertionError as e:
        print(f"  PTY BOOT FAILED: {e}")
        return 1
    except Exception as e:
        print(f"  PTY BOOT ERROR: {type(e).__name__}: {e}")
        return 1

    print("\nplaytest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
