"""Repair command - Repair corrupted archives using PAR2."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.logging import log_error, log_info, show_header


def main(
    archive_path: Annotated[
        Path,
        typer.Argument(
            help="Archive file to repair",
            exists=True,
            readable=True,
        ),
    ],
    verify_only: Annotated[
        bool, typer.Option("--verify-only", help="Only verify PAR2 files, don't repair")
    ] = False,
):
    """Repair corrupted archives using PAR2.

    Uses PAR2 recovery files to repair corrupted archives.
    Requires corresponding .par2 files to be present.

    New functionality not in bash scripts.
    """
    show_header("Cold Storage Standard - Repair", f"Repairing: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Mode: {'verify only' if verify_only else 'repair'}")

    # TODO: Implement actual repair logic
    log_error("Repair functionality not yet implemented")
    raise typer.Exit(1)
