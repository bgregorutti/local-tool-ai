"""CLI dispatcher: routes 'ai-agent [tui|gui]' to the appropriate entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="ai-agent",
        description="Local tool-calling agent powered by LM Studio.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="tui",
        choices=["tui", "gui"],
        help="Interface to launch (default: tui)",
    )
    args, remaining = parser.parse_known_args()

    os.environ["ALLOWED_ROOT"] = str(Path.cwd().resolve())

    # Strip the target arg so sub-commands (Typer / argparse) parse cleanly
    sys.argv = [sys.argv[0]] + remaining

    if args.target == "tui":
        from main import run as run_tui

        run_tui()
    else:
        from server import run as run_server

        run_server()
