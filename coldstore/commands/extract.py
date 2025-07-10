"""Extract command - Extract archives."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.logging import log_error, log_info, show_header

app = typer.Typer(help="Extract archives (equivalent to extract-archive.sh)")


@app.callback(invoke_without_command=True)
def extract(
    archive_path: Annotated[
        Path,
        typer.Argument(
            help="Archive file to extract",
            exists=True,
            readable=True,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Output directory for extracted files"),
    ] = Path.cwd(),
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force extraction even if directory exists"),
    ] = False,
):
    """Extract archives.

    Performs two-stage extraction:
    1. zstd decompression
    2. tar extraction

    Includes safe directory creation with overwrite protection.

    Equivalent to extract-archive.sh functionality.
    """
    show_header("Cold Storage Standard - Extract", f"Extracting: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Output directory: {output_dir}")
    log_info(f"Force overwrite: {'enabled' if force else 'disabled'}")

    # TODO: Implement actual extraction logic
    log_error("Extract functionality not yet implemented")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
