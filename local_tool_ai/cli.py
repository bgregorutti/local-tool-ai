"""CLI dispatcher: routes 'ai-agent [tui|gui|init]' to the appropriate entry point."""

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
        choices=["tui", "gui", "init"],
        help="tui (default) / gui (web UI) / init (one-time user-config setup)",
    )
    args, remaining = parser.parse_known_args()

    if args.target == "init":
        from local_tool_ai.init import run as run_init

        run_init()
        return

    os.environ["ALLOWED_ROOT"] = str(Path.cwd().resolve())

    # Strip the target arg so sub-commands (Typer / argparse) parse cleanly
    sys.argv = [sys.argv[0]] + remaining

    if args.target == "tui":
        from local_tool_ai.main import run as run_tui

        run_tui()
    else:
        from local_tool_ai.server import run as run_server

        run_server()
