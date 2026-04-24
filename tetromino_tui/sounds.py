"""One-shot sound effects.

SoundBoard.play(name) spawns a fire-and-forget subprocess that exits
when the WAV finishes. No loop, no cleanup needed. Silent on failure
(no player on this box, no WAV at that path, SSH without audio).

Namespaces:
    dealwaste   shuffle/deal at new-game
    flip        piece rotate / movement click
    nomove      illegal action / blocked rotate
    winwon      celebration and game-over hit
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SOUND_DIR = Path(__file__).resolve().parent / "assets" / "sound"


def _detect_player() -> list[str] | None:
    for cmd in (["paplay"], ["afplay"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


_PLAYER = _detect_player()


class SoundBoard:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and _PLAYER is not None

    @property
    def available(self) -> bool:
        return _PLAYER is not None

    def toggle(self) -> bool:
        self.enabled = not self.enabled and _PLAYER is not None
        return self.enabled

    def play(self, name: str) -> None:
        if not self.enabled or _PLAYER is None:
            return
        path = SOUND_DIR / name
        if not path.exists():
            return
        try:
            subprocess.Popen(
                [*_PLAYER, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                # Don't daemonize — a short SFX finishes in <1s and a
                # new-session orphan would be uglier than a brief zombie.
            )
        except (OSError, FileNotFoundError):
            self.enabled = False
