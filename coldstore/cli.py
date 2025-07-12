"""Cold Storage Standard CLI - Main command-line interface."""

from typing import Annotated

import typer
from rich.console import Console

from coldstore.logging import setup_logging

app = typer.Typer(
    name="coldstore",
    help="Standardized cold storage solution for research data and experimental results",
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress non-essential output")
    ] = False,
):
    """Cold Storage Standard CLI."""
    # Store global options in context for commands to access
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    setup_logging(verbose=verbose, quiet=quiet)


def _register_commands():
    """Register CLI commands to avoid circular imports."""
    # Import commands after app is defined to avoid circular imports
    from coldstore.commands.extract import main as extract_command
    from coldstore.commands.pack import main as pack_command
    from coldstore.commands.process import main as process_command
    from coldstore.commands.repair import main as repair_command
    from coldstore.commands.verify import main as verify_command

    app.command("pack", help="Convert archives to cold storage format")(pack_command)
    app.command("verify", help="Verify archive integrity")(verify_command)
    app.command("extract", help="Extract archives")(extract_command)
    app.command("repair", help="Repair corrupted archives using PAR2")(repair_command)
    app.command("process", help="Verify and extract archives")(process_command)


# Register commands
_register_commands()


if __name__ == "__main__":
    app()
