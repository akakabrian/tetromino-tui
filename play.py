"""Entry point — `python play.py [--level N] [--seed N]`."""

from __future__ import annotations

import argparse

from tetromino_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="tetromino-tui")
    p.add_argument("--level", type=int, default=1,
                   help="starting level (1..20, default 1)")
    p.add_argument("--seed", type=int, default=None,
                   help="RNG seed (for deterministic piece sequences / demos)")
    p.add_argument("--music", action="store_true",
                   help="start with background music enabled")
    p.add_argument("--no-sound", action="store_true",
                   help="disable sound effects")
    args = p.parse_args()
    if not 1 <= args.level <= 20:
        p.error("level must be in 1..20")
    run(start_level=args.level, seed=args.seed,
        music=args.music, sound=not args.no_sound)


if __name__ == "__main__":
    main()
