"""Verify command - Verify archive integrity."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.logging import log_error, log_info, show_header


def main(
    archive_path: Annotated[
        Path,
        typer.Argument(
            help="Archive file to verify",
            exists=True,
            readable=True,
        ),
    ],
    directory: Annotated[
        bool, typer.Option("--directory", "-d", help="Verify all archives in directory")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed verification output")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress non-essential output")
    ] = False,
):
    """Verify archive integrity.

    Performs 5-layer verification:
    1. zstd integrity check
    2. SHA-256 hash verification
    3. BLAKE3 hash verification
    4. PAR2 integrity check
    5. tar content verification

    Equivalent to verify-archive.sh functionality.
    """
    show_header("Cold Storage Standard - Verify", f"Verifying: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Mode: {'directory batch' if directory else 'single file'}")
    log_info(f"Verbose: {'enabled' if verbose else 'disabled'}")

    # TODO: Implement actual verification logic
    log_error("Verify functionality not yet implemented")
    raise typer.Exit(1)
