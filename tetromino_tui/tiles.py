"""Tile / piece colors and glyphs.

Guideline color convention (clean-room — the colors are just CMY plus
yellow plus green/orange/purple/cyan, a trivial palette; the colors
aren't copyrightable, and we derived them from public wiki content):

    I  cyan
    O  yellow
    T  purple
    S  green
    Z  red
    J  blue
    L  orange

We render each tile as TWO terminal columns wide so the grid reads as
a square (terminal cells are ~2:1 tall:wide). Characters: a solid
block "██" for locked / active cells; dim "▓▓" isn't necessary because
the background color already carries the distinction.
"""

from __future__ import annotations

from rich.style import Style


# (fg, bg) per piece letter. Bright fg on deep bg so filled blocks pop
# against the matrix grid background.
_PALETTE: dict[str, tuple[str, str]] = {
    "I": ("rgb(40,230,230)", "rgb(20,90,95)"),
    "O": ("rgb(250,220,50)", "rgb(100,85,20)"),
    "T": ("rgb(200,95,230)", "rgb(80,30,100)"),
    "S": ("rgb(90,230,110)", "rgb(30,95,40)"),
    "Z": ("rgb(240,80,80)", "rgb(100,30,30)"),
    "J": ("rgb(70,110,250)", "rgb(25,40,100)"),
    "L": ("rgb(245,160,60)", "rgb(100,65,20)"),
}

# Background for empty matrix cells + gutter.
EMPTY_BG = "rgb(24,22,30)"
GRID_GUTTER_BG = "rgb(12,10,18)"
GHOST_DIM_BG = "rgb(30,28,38)"


# Pre-parsed Style objects — Style.parse is expensive per-cell; the
# tetris renderer would call it thousands of times per frame without this.
FILLED: dict[str, Style] = {}
FILLED_BRIGHT: dict[str, Style] = {}
GHOST: dict[str, Style] = {}

for _piece, (_fg, _bg) in _PALETTE.items():
    FILLED[_piece] = Style.parse(f"bold {_fg} on {_bg}")
    FILLED_BRIGHT[_piece] = Style.parse(f"bold {_fg} on {_fg}")
    GHOST[_piece] = Style.parse(f"{_fg} on {GHOST_DIM_BG}")

EMPTY_STYLE = Style.parse(f"on {EMPTY_BG}")
GUTTER_STYLE = Style.parse(f"on {GRID_GUTTER_BG}")


def filled_style(piece: str, *, flash: bool = False) -> Style:
    """Style for a locked / active cell. `flash=True` is used for the
    line-clear flash animation — swaps to fg-on-fg so the row looks
    solid bright for one frame."""
    if piece not in FILLED:
        # Unknown piece letter → loud magenta so dev notices, don't crash.
        return Style.parse("bold white on rgb(200,0,200)")
    return FILLED_BRIGHT[piece] if flash else FILLED[piece]


def ghost_style(piece: str) -> Style:
    if piece not in GHOST:
        return Style.parse(f"white on {GHOST_DIM_BG}")
    return GHOST[piece]


# The block glyph — two columns wide per matrix cell.
CELL_GLYPH = "  "       # 2 spaces with a bg color = solid rectangle
CELL_WIDTH = 2          # matrix cells are 2 terminal columns each

# For the ghost and preview panels we use a lighter fill so the piece
# reads as "outline" against a darker bg.
GHOST_GLYPH = "░░"
