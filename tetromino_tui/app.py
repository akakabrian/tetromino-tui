"""Textual app for tetromino-tui ("Terminal Blocks").

Layout:
    +---------------------+---------------+
    |                     |  NEXT         |
    |                     |               |
    |    MATRIX (10x20)   +---------------+
    |                     |  HOLD         |
    |                     +---------------+
    |                     |  STATS        |
    |                     |  score/lines  |
    |                     |  level/time   |
    +---------------------+---------------+
    flash-bar (1 row)

Keys:
    ← →           move left/right
    ↓             soft drop (hold for continuous)
    space         hard drop
    z             rotate CCW
    x, ↑          rotate CW
    c             hold
    p             pause
    n             new game
    h             toggle high-scores
    g             toggle ghost piece
    s             toggle sound
    ?             help
    q             quit
"""

from __future__ import annotations

import time

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

from . import pieces as pcs
from . import tiles
from .engine import (
    Game, BUFFER_H, MATRIX_H, MATRIX_W, VISIBLE_H,
)
from . import state as state_mod
from .music import MusicPlayer
from .screens import ConfirmScreen, GameOverScreen, HighScoresScreen
from .sounds import SoundBoard


# Tick cadence — the engine runs its gravity in `tick(dt)` so we can
# just feed it wall-clock deltas. 60 Hz is overkill but cheap.
TICK_HZ = 60.0
TICK_INTERVAL = 1.0 / TICK_HZ

# Line-clear flash duration (seconds).
LINE_FLASH_S = 0.25


class MatrixView(Widget):
    """Renders the 10×20 visible matrix + ghost + active piece overlay.

    Full-viewport refresh per piece move or tick — the matrix is 10×20
    = 200 cells, rendering all of them is sub-millisecond and simpler
    than row-level invalidation."""

    # Animation reactive — bumped by the app's tick timer. Triggers a
    # refresh when its value changes.
    frame_counter: reactive[int] = reactive(0)
    # Line-clear flash — set by the app when a clear happens, decays
    # over LINE_FLASH_S. Stored as a monotonic-time deadline.
    _flash_until: float = 0.0
    _flash_rows: list[int]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.ghost_enabled = True
        self._flash_rows = []

    def on_mount(self) -> None:
        self.refresh()

    def watch_frame_counter(self, old: int, new: int) -> None:
        if self.is_mounted:
            self.refresh()

    # ---- flash triggers ------------------------------------------------

    def trigger_line_flash(self, rows: list[int]) -> None:
        """Called by the app after a line clear event."""
        self._flash_rows = list(rows)
        self._flash_until = time.monotonic() + LINE_FLASH_S
        self.refresh()

    def _flash_active(self) -> bool:
        return time.monotonic() < self._flash_until

    # ---- sizing helpers -----------------------------------------------

    def matrix_pixel_size(self) -> tuple[int, int]:
        """Width/height of the visible matrix in terminal cells."""
        return (MATRIX_W * tiles.CELL_WIDTH, VISIBLE_H)

    # ---- render_line ---------------------------------------------------

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        grid_w, grid_h = self.matrix_pixel_size()
        off_x = max(0, (width - grid_w) // 2)
        off_y = max(0, (height - grid_h) // 2)
        # Outside the grid — fill with gutter color.
        if y < off_y or y >= off_y + grid_h:
            return Strip([Segment(" " * width, tiles.GUTTER_STYLE)], width)

        # Map widget-row y → matrix row index (skip BUFFER_H hidden rows).
        matrix_y = BUFFER_H + (y - off_y)

        # Build a palette of cell→(piece,letter) for this row:
        #   - locked cells from game.grid
        #   - ghost piece cells (if enabled and not obscured by locked)
        #   - active piece cells
        # Active overrides ghost overrides locked.
        row_cells: list[str] = ["" for _ in range(MATRIX_W)]
        row_kind: list[str] = ["empty"] * MATRIX_W  # "empty","locked","ghost","active"

        for x, letter in enumerate(self.game.grid[matrix_y]):
            if letter:
                row_cells[x] = letter
                row_kind[x] = "locked"

        if self.ghost_enabled:
            for (gx, gy, letter) in self.game.ghost_cells():
                if gy == matrix_y and row_kind[gx] == "empty":
                    row_cells[gx] = letter
                    row_kind[gx] = "ghost"

        for (ax, ay, letter) in self.game.active_cells():
            if ay == matrix_y:
                row_cells[ax] = letter
                row_kind[ax] = "active"

        flashing_row = (matrix_y in self._flash_rows and self._flash_active())

        segs: list[Segment] = []
        if off_x > 0:
            segs.append(Segment(" " * off_x, tiles.GUTTER_STYLE))

        for x in range(MATRIX_W):
            letter = row_cells[x]
            kind = row_kind[x]
            if kind == "empty":
                segs.append(Segment(tiles.CELL_GLYPH, tiles.EMPTY_STYLE))
            elif kind == "ghost":
                segs.append(Segment(tiles.GHOST_GLYPH,
                                    tiles.ghost_style(letter)))
            else:
                # locked or active
                style = tiles.filled_style(letter, flash=flashing_row)
                segs.append(Segment(tiles.CELL_GLYPH, style))

        right_pad = width - off_x - grid_w
        if right_pad > 0:
            segs.append(Segment(" " * right_pad, tiles.GUTTER_STYLE))
        return Strip(segs, width)


# ---------- side panels -------------------------------------------------

def _render_piece_minigrid(piece: str, rotation: int = 0) -> Text:
    """Render a 4x2-row text preview of a piece (for next/hold panels).
    Each cell is 2 terminal columns so the proportion stays square-ish.
    Returns a rich.Text with styled segments."""
    t = Text()
    offsets = set(pcs.shape_cells(piece, rotation))
    # Crop to the piece's own bounding box so small pieces aren't surrounded
    # by excess whitespace (I fills 4x1 visibly in R0; O fills 2x2 etc.).
    xs = [x for (x, _y) in offsets]
    ys = [y for (_x, y) in offsets]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    style_on = tiles.filled_style(piece)
    style_off = Style.parse("on rgb(18,16,24)")
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if (x, y) in offsets:
                t.append("  ", style=style_on)
            else:
                t.append("  ", style=style_off)
        t.append("\n")
    return t


class NextPanel(Static):
    """Shows the next 5 upcoming pieces, stacked vertically."""

    def __init__(self, game: Game) -> None:
        super().__init__("")
        self.game = game
        self.border_title = "NEXT"
        self._last_queue: list[str] = []

    def refresh_panel(self) -> None:
        q = self.game.peek_queue()
        if q == self._last_queue:
            return
        self._last_queue = list(q)
        t = Text()
        for i, piece in enumerate(q):
            t.append(_render_piece_minigrid(piece))
            if i < len(q) - 1:
                t.append("\n\n")
        self.update(t)


class HoldPanel(Static):
    """Shows the hold slot piece (or '—' if empty) plus a hint about
    whether hold has been used this turn."""

    def __init__(self, game: Game) -> None:
        super().__init__("")
        self.game = game
        self.border_title = "HOLD"
        self._last: tuple[str | None, bool] = ("", False)

    def refresh_panel(self) -> None:
        snap = (self.game.hold, self.game._hold_used_this_turn)
        if snap == self._last:
            return
        self._last = snap
        if self.game.hold is None:
            self.update(Text.from_markup("[dim]empty[/]"))
        else:
            t = Text()
            t.append(_render_piece_minigrid(self.game.hold))
            if self.game._hold_used_this_turn:
                t.append("\n[locked]", style="dim")
            self.update(t)


class StatsPanel(Static):
    """Score / lines / level / time / pause / game-over banner."""

    def __init__(self, game: Game) -> None:
        super().__init__("")
        self.game = game
        self.border_title = "STATS"
        self._pulse_phase = False

    def refresh_panel(self, *, force: bool = False) -> None:
        if force:
            self._pulse_phase = not self._pulse_phase
        s = self.game.state()
        t = Text()
        t.append("Score  ", style="bold")
        t.append(f"{s['score']:>10,}\n", style="bold rgb(230,200,110)")
        t.append("Lines  ", style="bold")
        t.append(f"{s['lines']:>10}\n", style="rgb(200,230,120)")
        t.append("Level  ", style="bold")
        t.append(f"{s['level']:>10}\n", style="rgb(180,210,255)")
        elapsed = int(s["elapsed"])
        mm, ss = divmod(elapsed, 60)
        t.append("Time   ")
        t.append(f"{mm:>7d}:{ss:02d}\n", style="dim")
        t.append(f"Pieces   {s['pieces_locked']:>8}\n", style="dim")
        if s["b2b"]:
            t.append("B2B streak active\n", style="bold rgb(230,200,110)")
        t.append("\n")
        if s["game_over"]:
            bg = "rgb(170,40,40)" if self._pulse_phase else "rgb(130,20,20)"
            t.append("  GAME OVER  \n", style=f"bold white on {bg}")
            t.append("press [bold]n[/] for new game\n")
        elif s["paused"]:
            bg = "rgb(230,200,110)" if self._pulse_phase else "rgb(180,160,70)"
            t.append("  PAUSED  \n", style=f"bold black on {bg}")
            t.append("press [bold]p[/] to resume\n")
        else:
            t.append("←→ move   ↓ soft   space hard\n", style="dim")
            t.append("z/x rotate   c hold   p pause\n", style="dim")
            t.append("h scores  g ghost  s sound\n", style="dim")
            t.append("? help    n new    q quit\n", style="dim")
        self.update(t)


class FlashBar(Static):
    """One-line transient message — 'TETRIS!', 'double', 'held', etc."""
    def set_message(self, msg: str) -> None:
        self.update(Text.from_markup(msg))


class TopHUD(Horizontal):
    """Top chrome: title / time / moves / score."""

    def compose(self) -> ComposeResult:
        yield Static("◆ TERMINAL BLOCKS ◆", id="hud-title")
        yield Static("TIME 0:00", id="hud-time")
        yield Static("MOVES 0", id="hud-moves")
        yield Static("SCORE 0", id="hud-score")

    def refresh_hud(self, app: "TetrisApp") -> None:
        if not self.is_mounted:
            return
        s = app.game.state()
        elapsed = int(s["elapsed"])
        mm, ss = divmod(elapsed, 60)
        try:
            app.query_one("#hud-title", Static).update("◆ TERMINAL BLOCKS ◆")
            app.query_one("#hud-time", Static).update(f"TIME {mm}:{ss:02d}")
            app.query_one("#hud-moves", Static).update(
                f"MOVES {s['pieces_locked']}"
            )
            app.query_one("#hud-score", Static).update(
                f"SCORE {s['score']:,} · L{s['level']} · {s['lines']}L"
            )
        except Exception:
            return


_HELP_TEXT = (
    "[bold]Terminal Blocks[/]\n\n"
    "[bold]Goal[/]  clear rows by filling them end-to-end.\n"
    "       Clearing 4 rows at once is a [bold rgb(230,200,110)]"
    "tetris[/] and scores double.\n\n"
    "[bold]Keys[/]\n"
    "  ←→            move left/right\n"
    "  ↓             soft drop (1 pt/cell)\n"
    "  space         hard drop (2 pts/cell, locks immediately)\n"
    "  z             rotate counter-clockwise\n"
    "  x or ↑        rotate clockwise\n"
    "  c             hold / swap (one per piece)\n"
    "  p             pause\n"
    "  n             new game\n"
    "  h             high scores\n"
    "  g             ghost piece on/off\n"
    "  s             sound on/off\n"
    "  m             music on/off\n"
    "  ?             toggle this help\n"
    "  q             quit\n\n"
    "[bold]Scoring[/]  single/double/triple/tetris = 100/300/500/800 × level\n"
    "          consecutive tetrises get a back-to-back 1.5× bonus.\n"
    "          Level up every 10 lines cleared.\n\n"
    "[bold]Music credits[/]\n"
    "  Chiptune Tchaikovsky — Tomasz Kucza, CC-BY 4.0\n"
    "  Cyberpunk Moonlight Sonata — Joth, CC0 1.0\n\n"
    "[dim]press any key to dismiss[/]"
)


class HelpOverlay(Static):
    def __init__(self) -> None:
        super().__init__(Text.from_markup(_HELP_TEXT))
        self.border_title = "HELP"
        self.display = False


# ---------- main App ----------------------------------------------------

class TetrisApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "Terminal Blocks"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_game", "New"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("c", "hold_piece", "Hold"),
        Binding("h", "toggle_scores", "Scores"),
        Binding("g", "toggle_ghost", "Ghost"),
        Binding("s", "toggle_sound", "Sound"),
        Binding("m", "toggle_music", "Music"),
        Binding("question_mark", "toggle_help", "Help"),
        # Movement — priority so nothing eats them.
        Binding("left",  "move('left')",  "←", show=False, priority=True),
        Binding("right", "move('right')", "→", show=False, priority=True),
        Binding("down",  "soft_drop",     "↓", show=False, priority=True),
        Binding("up",    "rotate_cw",     "Rot", show=False, priority=True),
        Binding("space", "hard_drop",     "Drop", priority=True),
        Binding("z",     "rotate_ccw",    "z", show=False, priority=True),
        Binding("x",     "rotate_cw",     "x", show=False, priority=True),
    ]

    def __init__(self, *, start_level: int = 1, seed: int | None = None,
                 music: bool = False, sound: bool = True) -> None:
        super().__init__()
        self._state = state_mod.load()
        self._start_level = start_level
        self._seed = seed
        self._music_enabled = music
        self.game = Game(start_level=start_level, seed=seed)
        self.matrix_view = MatrixView(self.game)
        self.matrix_view.ghost_enabled = bool(
            state_mod.get_setting(self._state, "ghost", True))
        self.next_panel = NextPanel(self.game)
        self.hold_panel = HoldPanel(self.game)
        self.stats_panel = StatsPanel(self.game)
        self.top_hud = TopHUD(id="top-hud")
        self.flash_bar = FlashBar(" ", id="flash-bar")
        self.help_overlay = HelpOverlay()
        self.help_overlay.id = "help-overlay"
        # Sound defaults from settings unless disabled via CLI.
        enabled = bool(state_mod.get_setting(self._state, "sound", False)) and sound
        self.sounds = SoundBoard(enabled=enabled)
        self.music = MusicPlayer(enabled=self._music_enabled)
        # Tick bookkeeping.
        self._last_tick_mono: float | None = None
        # True if we've already recorded a high score for this game-over
        # event, so we don't re-submit on every tick.
        self._high_score_recorded = False

    # ---- RL hooks (headless; no Textual required) ----------------------

    def game_state_vector(self):
        from . import rl_hooks
        return rl_hooks.state_vector(self.game)

    def game_reward(self, prev_score: int = 0,
                    prev_game_over: bool = False) -> float:
        from . import rl_hooks
        return rl_hooks.compute_reward(prev_score, prev_game_over, self.game)

    def is_terminal(self) -> bool:
        from . import rl_hooks
        return rl_hooks.is_terminal(self.game)

    def reset_game(self) -> None:
        self.game = Game(start_level=self._start_level, seed=self._seed)

    # ---- layout --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield self.top_hud
        with Horizontal(id="body"):
            with Vertical(id="matrix-col"):
                yield self.matrix_view
            with Vertical(id="side"):
                yield self.next_panel
                yield self.hold_panel
                yield self.stats_panel
        yield self.flash_bar
        yield self.help_overlay

    async def on_mount(self) -> None:
        self.matrix_view.border_title = "MATRIX"
        self.music.start()
        self._refresh_all_panels()
        self._show_hint()
        self._update_header()
        self._refresh_hud()
        # 60 Hz gravity tick.
        self.set_interval(TICK_INTERVAL, self._tick)
        # 2 Hz pulse — cheap status-panel repaint for banner shimmer.
        self.set_interval(0.5, self._pulse)
        # 1 Hz top HUD ticker for elapsed time + score.
        self.set_interval(1.0, self._refresh_hud)

    async def on_unmount(self) -> None:
        self.music.stop()

    # ---- helpers -------------------------------------------------------

    def _refresh_all_panels(self) -> None:
        self.matrix_view.refresh()
        self.next_panel.refresh_panel()
        self.hold_panel.refresh_panel()
        self.stats_panel.refresh_panel()

    def _update_header(self) -> None:
        s = self.game.state()
        bits = []
        if s["paused"]:
            bits.append("PAUSED")
        if s["game_over"]:
            bits.append("GAME OVER")
        bits.append(f"score {s['score']:,}")
        bits.append(f"L{s['level']}")
        bits.append(f"{s['lines']}ln")
        self.sub_title = "  ·  ".join(bits)

    def _show_hint(self) -> None:
        s = self.game.state()
        if s["game_over"]:
            self.flash_bar.set_message(
                "[red]GAME OVER[/] — press [bold]n[/] for a new game"
            )
        elif s["paused"]:
            self.flash_bar.set_message(
                "[yellow]paused[/] — press [bold]p[/] to resume"
            )
        else:
            self.flash_bar.set_message(
                "[dim]←→ move · ↑/x rotate · z CCW · space drop · c hold · m music[/]"
            )

    def _pulse(self) -> None:
        self.stats_panel.refresh_panel(force=True)

    def _refresh_hud(self) -> None:
        self.top_hud.refresh_hud(self)

    # ---- ticker --------------------------------------------------------

    def _tick(self) -> None:
        """Called ~60 Hz. Advance gravity, drain events, trigger flashes."""
        now = time.monotonic()
        if self._last_tick_mono is None:
            self._last_tick_mono = now
            return
        dt = now - self._last_tick_mono
        self._last_tick_mono = now
        if self.help_overlay.display:
            return  # freeze while help is up
        before_level = self.game.level
        events = self.game.tick(dt)
        # Drain any lock events (for sound).
        lock_events = self.game.pop_lock_events()
        for le in lock_events:
            self.sounds.play("lock")
        # Line clear events — trigger flash, pick sound.
        if events:
            all_rows: list[int] = []
            msgs: list[str] = []
            for ev in events:
                all_rows.extend(ev.rows)
                if ev.count == 4:
                    self.sounds.play("tetris")
                    msgs.append("[bold rgb(230,200,110)]TETRIS![/]")
                elif ev.count == 3:
                    self.sounds.play("clear")
                    msgs.append("[bold rgb(200,230,120)]triple![/]")
                elif ev.count == 2:
                    self.sounds.play("clear")
                    msgs.append("[bold]double[/]")
                elif ev.count == 1:
                    self.sounds.play("clear")
                    msgs.append("[dim]single[/]")
            self.matrix_view.trigger_line_flash(all_rows)
            self.flash_bar.set_message(" · ".join(msgs))
            self.hold_panel.refresh_panel()  # hold-used may have changed
            self.next_panel.refresh_panel()
        # Level up detection.
        if self.game.level != before_level:
            self.sounds.play("levelup")
            self.flash_bar.set_message(
                f"[bold rgb(180,210,255)]LEVEL {self.game.level}[/]"
            )
        # Game-over detection — fire sound + push screen once.
        if self.game.game_over and not self._high_score_recorded:
            self._handle_game_over()
        # Matrix refresh every tick — the piece is moving via gravity and
        # the animation-flash timer decays. Cost is negligible (10x20).
        self.matrix_view.frame_counter = self.matrix_view.frame_counter + 1
        # Stats panel refresh isn't needed every tick — the 2 Hz pulse
        # handles the time counter. But we DO need it when the score
        # changes, so push a refresh here for correctness.
        self.stats_panel.refresh_panel()
        self._refresh_hud()
        self._update_header()

    def _handle_game_over(self) -> None:
        self._high_score_recorded = True
        self.sounds.play("gameover")
        # Record high score + see if it ranks.
        s = self.game.state()
        scores_before = list(self._state.get("high_scores", []))
        top_before = max((e["score"] for e in scores_before), default=-1)
        state_mod.add_high_score(
            self._state, score=s["score"], lines=s["lines"],
            level=s["level"],
        )
        state_mod.save(self._state)
        rank = None
        for i, e in enumerate(self._state["high_scores"], start=1):
            if (e["score"] == s["score"] and e["lines"] == s["lines"]
                    and e["level"] == s["level"]):
                rank = i
                break
        new_best = s["score"] > top_before and s["score"] > 0
        # Push the game-over screen (unless help is up — then just flash).
        if self.help_overlay.display:
            self.flash_bar.set_message("[red]GAME OVER[/]")
            return

        def _after(choice) -> None:
            if choice == "new":
                self._do_new_game()

        self.push_screen(
            GameOverScreen(score=s["score"], lines=s["lines"],
                           level=s["level"], rank=rank, new_best=new_best),
            _after,
        )

    # ---- action handlers ----------------------------------------------

    def _maybe_dismiss_help(self) -> bool:
        """If help is up, dismiss it and return True (caller should bail)."""
        if self.help_overlay.display:
            self.help_overlay.display = False
            return True
        return False

    def _after_input(self) -> None:
        """Post-input refresh. Cheap; we do it after every key."""
        self._refresh_all_panels()
        self._refresh_hud()
        self._update_header()

    def action_move(self, direction: str) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        verb = "left" if direction == "left" else "right"
        ok = self.game.action(verb)
        if ok:
            self.sounds.play("move")
        self._after_input()

    def action_soft_drop(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        self.game.action("soft_drop")
        self._after_input()

    def action_hard_drop(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        self.game.action("hard_drop")
        # Hard drop locks the piece immediately → drain lock/line events
        # synchronously so the flash fires with the same keystroke.
        for le in self.game.pop_lock_events():
            self.sounds.play("lock")
        evs = self.game.pop_events()
        if evs:
            rows: list[int] = []
            for ev in evs:
                rows.extend(ev.rows)
                if ev.count == 4:
                    self.sounds.play("tetris")
                    self.flash_bar.set_message(
                        "[bold rgb(230,200,110)]TETRIS![/]")
                else:
                    self.sounds.play("clear")
            self.matrix_view.trigger_line_flash(rows)
        if self.game.game_over and not self._high_score_recorded:
            self._handle_game_over()
        self._after_input()

    def action_rotate_cw(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        if self.game.action("rotate_cw"):
            self.sounds.play("rotate")
        self._after_input()

    def action_rotate_ccw(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        if self.game.action("rotate_ccw"):
            self.sounds.play("rotate")
        self._after_input()

    def action_hold_piece(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over or self.game.paused:
            return
        if self.game.action("hold"):
            self.sounds.play("hold")
            self.flash_bar.set_message("[dim]held[/]")
        else:
            self.flash_bar.set_message("[dim]hold already used[/]")
        self._after_input()

    def action_new_game(self) -> None:
        if self._maybe_dismiss_help():
            return
        # If there's a substantial in-progress game, confirm.
        s = self.game.state()
        if (not s["game_over"] and s["score"] >= 500
                and s["pieces_locked"] >= 10):
            def _after(ok):
                if ok:
                    self._do_new_game()
                else:
                    self.flash_bar.set_message("[dim]kept current game[/]")
            self.push_screen(
                ConfirmScreen(
                    f"Start a new game? "
                    f"Current score [bold]{s['score']:,}[/] will be lost."
                ),
                _after,
            )
            return
        self._do_new_game()

    def _do_new_game(self) -> None:
        self.game = Game(start_level=self._start_level, seed=self._seed)
        self.matrix_view.game = self.game
        self.matrix_view._flash_rows = []
        self.matrix_view._flash_until = 0.0
        self.next_panel.game = self.game
        self.next_panel._last_queue = []
        self.hold_panel.game = self.game
        self.hold_panel._last = ("", False)
        self.stats_panel.game = self.game
        self._high_score_recorded = False
        self._refresh_all_panels()
        self.flash_bar.set_message("[bold green]new game[/]")
        self._update_header()

    def action_toggle_pause(self) -> None:
        if self._maybe_dismiss_help():
            return
        if self.game.game_over:
            self.flash_bar.set_message("[dim]can't pause a finished game[/]")
            return
        paused = self.game.toggle_pause()
        self.flash_bar.set_message(
            "[yellow]paused[/]" if paused else "[green]resumed[/]"
        )
        self._after_input()

    def action_toggle_help(self) -> None:
        self.help_overlay.display = not self.help_overlay.display

    def action_toggle_scores(self) -> None:
        if self._maybe_dismiss_help():
            return
        # Reload state from disk so newly-added scores show up.
        self._state = state_mod.load()
        self.push_screen(HighScoresScreen(self._state))

    def action_toggle_ghost(self) -> None:
        if self._maybe_dismiss_help():
            return
        self.matrix_view.ghost_enabled = not self.matrix_view.ghost_enabled
        state_mod.set_setting(self._state, "ghost",
                              self.matrix_view.ghost_enabled)
        state_mod.save(self._state)
        self.flash_bar.set_message(
            "[dim]ghost "
            + ("on" if self.matrix_view.ghost_enabled else "off")
            + "[/]"
        )
        self.matrix_view.refresh()

    def action_toggle_sound(self) -> None:
        if self._maybe_dismiss_help():
            return
        if not self.sounds.available:
            self.flash_bar.set_message(
                "[red]no audio player found[/] "
                "(install paplay / aplay / afplay)"
            )
            return
        on = self.sounds.toggle()
        state_mod.set_setting(self._state, "sound", on)
        state_mod.save(self._state)
        self.flash_bar.set_message(
            f"[bold {'green' if on else 'yellow'}]"
            f"sound {'on' if on else 'off'}[/]"
        )

    def action_toggle_music(self) -> None:
        if self._maybe_dismiss_help():
            return
        on = self.music.toggle()
        self.flash_bar.set_message(
            f"[bold {'green' if on else 'yellow'}]"
            f"music {'on' if on else 'off'}[/]"
        )


def run(*, start_level: int = 1, seed: int | None = None,
        music: bool = False, sound: bool = True) -> None:
    app = TetrisApp(start_level=start_level, seed=seed,
                    music=music, sound=sound)
    try:
        app.run()
    finally:
        app.music.stop()
        # Terminal mouse tracking reset (inherited discipline).
        import sys
        sys.stdout.write(
            "\033[?1000l\033[?1002l\033[?1003l"
            "\033[?1006l\033[?1015l\033[?25h"
        )
        sys.stdout.flush()
