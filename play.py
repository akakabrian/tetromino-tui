"""Entry point — `python play.py [--level N] [--seed N]`."""

from __future__ import annotations

import argparse

from tetris_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="tetris-tui")
    p.add_argument("--level", type=int, default=1,
                   help="starting level (1..20, default 1)")
    p.add_argument("--seed", type=int, default=None,
                   help="RNG seed (for deterministic piece sequences / demos)")
    args = p.parse_args()
    if not 1 <= args.level <= 20:
        p.error("level must be in 1..20")
    run(start_level=args.level, seed=args.seed)


if __name__ == "__main__":
    main()
