"""Pack command - Convert archives to cold storage format."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.logging import log_error, log_info, show_header

app = typer.Typer(
    help="Convert archives to cold storage format (equivalent to archive-compress.sh)"
)


@app.callback(invoke_without_command=True)
def pack(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="Input directory or archive file to process",
            exists=True,
            readable=True,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir", "-o", help="Output directory for processed archives"
        ),
    ] = Path("processed"),
    level: Annotated[
        int,
        typer.Option(
            "--level",
            "-l",
            help="Compression level (1-22, default: 19)",
            min=1,
            max=22,
        ),
    ] = 19,
    threads: Annotated[
        int,
        typer.Option(
            "--threads",
            "-t",
            help="Number of threads (0=auto, default: 0)",
            min=0,
        ),
    ] = 0,
    flat: Annotated[
        bool,
        typer.Option(
            "--flat", help="Use flat structure instead of organized subdirectories"
        ),
    ] = False,
    no_long: Annotated[
        bool,
        typer.Option(
            "--no-long", help="Disable long-distance matching (reduces memory usage)"
        ),
    ] = False,
    no_check: Annotated[
        bool,
        typer.Option(
            "--no-check", help="Skip integrity verification after compression"
        ),
    ] = False,
):
    """Convert archives to cold storage format.

    This command processes 7z/zip/rar files and converts them to verified
    tar.zst archives with SHA-256, BLAKE3, and PAR2 protection.

    Equivalent to archive-compress.sh functionality.
    """
    show_header("Cold Storage Standard - Pack", f"Processing: {input_path}")

    log_info(f"Input: {input_path}")
    log_info(f"Output directory: {output_dir}")
    log_info(f"Compression level: {level}")
    log_info(f"Threads: {threads if threads > 0 else 'auto'}")
    log_info(f"Structure: {'flat' if flat else 'organized'}")
    log_info(f"Long-distance matching: {'disabled' if no_long else 'enabled'}")
    log_info(f"Integrity check: {'disabled' if no_check else 'enabled'}")

    # TODO: Implement actual packing logic
    log_error("Pack functionality not yet implemented")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
