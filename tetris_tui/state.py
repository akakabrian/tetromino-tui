"""Persistence — high-score table + settings.

`$XDG_DATA_HOME/tetris-tui/state.json` (falls back to
`~/.local/share/tetris-tui/`). Schema:

    {
      "high_scores": [
        {"score": 12345, "lines": 54, "level": 6, "date": "2026-04-23"},
        ...
      ],
      "settings": {"sound": false, "ghost": true}
    }

We never crash on a bad save file — corrupt files are renamed aside and
the app starts with defaults. Top-10 high scores are kept.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any


MAX_HIGH_SCORES = 10


def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "tetris-tui"
    return Path.home() / ".local" / "share" / "tetris-tui"


STATE_PATH = _data_dir() / "state.json"


DEFAULT_STATE: dict[str, Any] = {
    "high_scores": [],
    "settings": {"sound": False, "ghost": True},
}


def load() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return _default_copy()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        try:
            STATE_PATH.rename(STATE_PATH.with_suffix(".corrupt.json"))
        except OSError:
            pass
        return _default_copy()
    data.setdefault("high_scores", [])
    data.setdefault("settings", {})
    data["settings"].setdefault("sound", False)
    data["settings"].setdefault("ghost", True)
    return data


def _default_copy() -> dict[str, Any]:
    import copy
    return copy.deepcopy(DEFAULT_STATE)


def save(data: dict[str, Any]) -> None:
    """Atomic write — tmp + rename."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(STATE_PATH)


def add_high_score(data: dict[str, Any], *, score: int, lines: int,
                   level: int, when: str | None = None) -> bool:
    """Add a score to the high-score table if it qualifies. Returns True
    if the score made it in."""
    entry = {
        "score": int(score),
        "lines": int(lines),
        "level": int(level),
        "date": when or date.today().isoformat(),
    }
    scores = list(data.get("high_scores", []))
    scores.append(entry)
    scores.sort(key=lambda e: e["score"], reverse=True)
    scores = scores[:MAX_HIGH_SCORES]
    data["high_scores"] = scores
    return entry in scores


def top_score(data: dict[str, Any]) -> int:
    scores = data.get("high_scores") or []
    if not scores:
        return 0
    return int(max(e["score"] for e in scores))


def get_setting(data: dict[str, Any], key: str, default: Any = None) -> Any:
    return data.get("settings", {}).get(key, default)


def set_setting(data: dict[str, Any], key: str, value: Any) -> None:
    data.setdefault("settings", {})[key] = value
