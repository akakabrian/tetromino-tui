"""Modal screens — high-score table, game-over, confirm.

Per the tui-game-build skill: priority=True App bindings (movement
arrows) beat ModalScreen bindings. Inside modals we stick to
non-conflicting keys (y/n/escape/q/space).

Textual 8+ warning: `Static(rich_text_object, id=...)` can crash the
compositor. Pass a markup string (plain `str`) to `super().__init__`.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from . import state as state_mod


class HighScoresScreen(ModalScreen[None]):
    """Top-10 table. Any key dismisses."""

    BINDINGS = [
        Binding("escape", "dismiss", "close"),
        Binding("q", "dismiss", "close"),
        Binding("enter", "dismiss", "close"),
        Binding("space", "dismiss", "close"),
    ]

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="scores-body"):
            yield Static(self._build_markup(), id="scores-content")
            yield Static("[dim]press any key to close[/]",
                         id="scores-dismiss")

    def _build_markup(self) -> str:
        scores = self._state.get("high_scores", []) or []
        lines: list[str] = []
        lines.append("[bold rgb(230,200,110)]HIGH SCORES[/]")
        lines.append("")
        if not scores:
            lines.append("[dim]no games finished yet — play one![/]")
        else:
            lines.append("  [bold]#   score    lines  lvl  date[/]")
            lines.append("")
            for i, e in enumerate(scores, start=1):
                lines.append(
                    f"  [bold]{i:>2}[/]  "
                    f"[rgb(230,200,110)]{int(e.get('score',0)):>7,}[/]  "
                    f"{int(e.get('lines',0)):>5}  "
                    f"{int(e.get('level',0)):>3}  "
                    f"[dim]{e.get('date','')}[/]"
                )
        lines.append("")
        lines.append(f"[dim]stored in {state_mod.STATE_PATH}[/]")
        return "\n".join(lines)

    def on_key(self, event) -> None:
        self.dismiss(None)


class RulesScreen(ModalScreen[None]):
    """Rules for the current variant, extracted from vendored PySolFC docs."""

    BINDINGS = [Binding("escape", "dismiss", show=False),
                Binding("q", "dismiss", show=False),
                Binding("r", "dismiss", show=False)]

    DEFAULT_CSS = """
    RulesScreen {
        align: center middle;
        background: #07190f 70%;
    }
    #rules-box {
        width: 80%;
        max-width: 88;
        height: auto;
        max-height: 90%;
        border: round #ffd45a;
        background: #07190f;
        padding: 1 2;
    }
    #rules-title {
        color: #ffd45a;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    #rules-body {
        color: #efe8d1;
    }
    #rules-foot {
        margin-top: 1;
        color: #8faa83;
        text-align: center;
    }
    """

    def __init__(self, variant: str, text: str) -> None:
        super().__init__()
        self._variant = variant
        self._text = text

    def compose(self) -> ComposeResult:
        from textual.containers import VerticalScroll
        with Vertical(id="rules-box"):
            yield Static(f"◆ {self._variant} — rules ◆", id="rules-title")
            with VerticalScroll():
                yield Static(self._text, id="rules-body")
            yield Static("[dim]Esc / r / q — close[/dim]", id="rules-foot")



class GameOverScreen(ModalScreen[str]):
    """Post-game summary — score / lines / level + hint. Returns a verb
    string ('new' or 'dismiss') when dismissed."""

    BINDINGS = [
        Binding("n", "new", "New game"),
        Binding("enter", "new", "New game"),
        Binding("escape", "close", "close"),
        Binding("q", "close", "close"),
        Binding("space", "close", "close"),
    ]

    def __init__(self, *, score: int, lines: int, level: int,
                 rank: int | None, new_best: bool,
                 elapsed: str = "0:00", seed: int | None = None) -> None:
        super().__init__()
        self._score = score
        self._lines = lines
        self._level = level
        self._rank = rank
        self._new_best = new_best
        self._elapsed = elapsed
        self._seed = seed

    def compose(self) -> ComposeResult:
        with Vertical(id="gameover-body"):
            yield Static(self._build_markup(), id="gameover-msg")
            yield Static(
                "[bold]n new game[/]   [bold]escape close[/]",
                id="gameover-keys",
            )

    def _build_markup(self) -> str:
        lines: list[str] = []
        lines.append(" ✦   ✦   ✦   ✦   ✦   ✦   ✦ ")
        lines.append("[bold rgb(240,120,120)]╔═ G A M E   O V E R ═╗[/]")
        lines.append(" ✦   ✦   ✦   ✦   ✦   ✦   ✦ ")
        lines.append("")
        lines.append(f"  Final score  [bold rgb(230,200,110)]"
                     f"{self._score:>8,}[/]")
        lines.append(f"  Lines        {self._lines:>8,}")
        lines.append(f"  Level        {self._level:>8,}")
        lines.append(f"  Time         {self._elapsed:>8}")
        lines.append(f"  Seed         {str(self._seed or 'random'):>8}")
        lines.append("")
        if self._new_best:
            lines.append("[bold rgb(240,220,100)]NEW PERSONAL BEST![/]")
        elif self._rank is not None:
            lines.append(f"[rgb(200,180,240)]ranked #{self._rank} "
                         "of your top 10[/]")
        else:
            lines.append("[dim]didn't crack the top 10 this time[/]")
        return "\n".join(lines)

    def action_new(self) -> None:
        self.dismiss("new")

    def action_close(self) -> None:
        self.dismiss("dismiss")


class ConfirmScreen(ModalScreen[bool]):
    """Generic yes/no confirm — used when starting a new game would
    discard an in-progress substantial game."""

    BINDINGS = [
        Binding("y", "confirm_yes", "yes"),
        Binding("n", "confirm_no", "no"),
        Binding("escape", "confirm_no", "cancel"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-body"):
            yield Static(self._message, id="confirm-msg")
            yield Static("[bold]y[/]es / [bold]n[/]o", id="confirm-keys")

    def action_confirm_yes(self) -> None:
        self.dismiss(True)

    def action_confirm_no(self) -> None:
        self.dismiss(False)
