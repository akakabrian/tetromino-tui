"""Background music — fire-and-forget looping subprocess.

Plays an MP3 from `tetromino_tui/assets/music/` via `paplay` (PulseAudio /
PipeWire on Linux) or `afplay` (macOS). Silent on failure — no audio
pipeline, SSH session, or missing player all degrade to a no-op rather
than exploding. Stop on app exit.

Format note: MP3 only. macOS `afplay` does not decode OGG; Linux
`aplay` does not decode MP3. paplay + afplay is the portable pair.
"""

from __future__ import annotations

import atexit
import ctypes
import os
import random
import shutil
import signal
import subprocess
import sys
from pathlib import Path


_ACTIVE: list["MusicPlayer"] = []


def _install_parent_death_trap() -> None:
    """On Linux, ask the kernel to SIGTERM us when the parent Python dies.

    Ensures the bash loop + paplay subprocess die whenever the Textual
    app exits — even on SIGKILL, terminal-window close, crash. macOS
    has no direct equivalent; we fall back to atexit + on_unmount.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        # PR_SET_PDEATHSIG = 1; signal.SIGTERM propagates cleanly.
        libc.prctl(1, signal.SIGTERM)
    except (OSError, AttributeError):
        pass


@atexit.register
def _kill_all_players() -> None:
    for p in list(_ACTIVE):
        try:
            p.stop()
        except Exception:
            pass


# Unique string that only our bash loop would contain — lets us find
# orphaned subprocesses from earlier crashes or concurrent instances.
_SIGNATURE = "tetromino_tui/assets/music/"


def _cleanup_orphans() -> None:
    """Kill any prior tetromino music bash loops + their paplay/afplay
    children. Safe to call multiple times; silently no-ops if nothing
    matches. Runs before every `start()` so a second launch doesn't
    stack audio on top of a first."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", _SIGNATURE],
            stderr=subprocess.DEVNULL,
        ).decode()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    import re
    my_pid = os.getpid()
    for line in out.splitlines():
        m = re.match(r"^(\d+)\s+", line)
        if not m:
            continue
        pid = int(m.group(1))
        if pid == my_pid:
            continue
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass


MUSIC_DIR = Path(__file__).resolve().parent / "assets" / "music"

# Tetris assignment (MP3-only for macOS afplay compatibility).
TRACKS: list[Path] = [
    MUSIC_DIR / "chiptune_tchaikovsky_looped.mp3",
    MUSIC_DIR / "cyberpunk_moonlight_sonata.mp3",
]

ATTRIBUTIONS = [
    "Chiptune Tchaikovsky — Tomasz Kucza, CC-BY 4.0",
    "Cyberpunk Moonlight Sonata — Joth, CC0 1.0",
]


def _detect_player() -> list[str] | None:
    for cmd in (["paplay"], ["afplay"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


class MusicPlayer:
    def __init__(self, enabled: bool = True,
                 tracks: list[Path] | None = None) -> None:
        self.tracks = [t for t in (tracks or TRACKS) if t.exists()]
        self.enabled = enabled and bool(self.tracks)
        self._player = _detect_player() if self.enabled else None
        self._proc: subprocess.Popen | None = None
        if self.enabled and self._player is None:
            self.enabled = False

    def start(self) -> None:
        if not self.enabled or self._proc is not None or not self.tracks:
            return
        # Kill any bash loops from prior / concurrent tetromino instances
        # before starting our own — otherwise two tracks play over each
        # other.
        _cleanup_orphans()
        track = random.choice(self.tracks)
        try:
            player_cmd = " ".join(self._player or [])
            # Signal-trapped loop: when bash receives SIGTERM/SIGINT/SIGHUP
            # (either from Python's stop(), from PR_SET_PDEATHSIG after the
            # parent dies, or from the terminal), it kills the backgrounded
            # paplay child *before* exiting — otherwise paplay would orphan
            # to init and keep playing after the terminal window closed.
            loop_cmd = (
                f'trap \'kill -TERM $(jobs -p) 2>/dev/null; exit 0\' TERM INT HUP; '
                f'while true; do {player_cmd} "{track}" >/dev/null 2>&1 & wait $!; done'
            )
            self._proc = subprocess.Popen(
                ["bash", "-c", loop_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                preexec_fn=_install_parent_death_trap,
            )
            if self not in _ACTIVE:
                _ACTIVE.append(self)
        except (OSError, FileNotFoundError):
            self.enabled = False

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self._proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        self._proc = None
        if self in _ACTIVE:
            _ACTIVE.remove(self)

    @property
    def is_playing(self) -> bool:
        return self._proc is not None

    def toggle(self) -> bool:
        """Flip mute state. Returns True if now playing."""
        if self.is_playing:
            self.stop()
            return False
        self.start()
        return self.is_playing
