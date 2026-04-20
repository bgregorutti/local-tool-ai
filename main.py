"""CLI entry point for the local tool-calling agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env before importing anything that reads env vars
from dotenv import load_dotenv
load_dotenv()

import typer
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import FileHistory
from rich.console import Console

import agent

app = typer.Typer(
    name="local-tool-ai",
    help="Local tool-calling agent powered by LM Studio.",
    add_completion=False,
)
console = Console()


@app.command()
def main(
    query: list[str] = typer.Argument(
        default=None,
        help="Query to run. Omit to start interactive REPL.",
    ),
    repl: bool = typer.Option(False, "--repl", "-r", help="Start interactive REPL mode."),
    system: str = typer.Option(
        agent.DEFAULT_SYSTEM,
        "--system",
        "-s",
        help="Override the system prompt.",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress step-by-step output."),
    model: str = typer.Option(
        None,
        "--model",
        "-m",
        help="Override LM_STUDIO_MODEL env var.",
    ),
    safe: bool = typer.Option(False, "--safe", help="Disable destructive tools (safe mode)."),
    enable_bash: bool = typer.Option(
        False, "--enable-bash", help="Enable run_bash tool (trusted environments only)."
    ),
) -> None:
    if safe:
        os.environ["SAFE_MODE"] = "1"
        console.print("[bold yellow]Running in safe mode — destructive tools disabled[/]")

    if enable_bash:
        os.environ["BASH_ENABLED"] = "1"
        console.print(
            "[bold yellow]⚠️  run_bash is enabled. Only use this in a trusted environment.[/]"
        )

    if model:
        os.environ["LM_STUDIO_MODEL"] = model

    if repl or not query:
        _run_repl(system=system, verbose=not quiet)
    else:
        user_query = " ".join(query)
        agent.run(user_query, system=system, verbose=not quiet)


def _run_repl(system: str, verbose: bool) -> None:
    console.print(
        "[bold green]Local Tool-AI REPL[/] — type [bold]exit[/] or press Ctrl-C to quit.\n"
    )
    while True:
        try:
            query = pt_prompt(">: ", history=FileHistory(".agent_history"))
        except (KeyboardInterrupt, EOFError):
            console.print("\nBye!")
            sys.exit(0)

        if query.strip().lower() in {"exit", "quit", "q"}:
            console.print("Bye!")
            sys.exit(0)

        if not query.strip():
            continue

        agent.run(query, system=system, verbose=verbose)
        console.print()


if __name__ == "__main__":
    app()
