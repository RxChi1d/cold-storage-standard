"""Cold Storage Standard CLI - Main command-line interface."""

from typing import Annotated

import typer
from rich.console import Console

from coldstore.commands import extract, pack, process, repair, verify
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
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose output")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress non-essential output")
    ] = False,
):
    """Cold Storage Standard CLI."""
    setup_logging(verbose=verbose, quiet=quiet)


app.add_typer(pack.app, name="pack", help="Convert archives to cold storage format")
app.add_typer(verify.app, name="verify", help="Verify archive integrity")
app.add_typer(extract.app, name="extract", help="Extract archives")
app.add_typer(repair.app, name="repair", help="Repair corrupted archives using PAR2")
app.add_typer(process.app, name="process", help="Verify and extract archives")


if __name__ == "__main__":
    app()
