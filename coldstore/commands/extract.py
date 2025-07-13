"""Extract command - Extract archives."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.core.compress import create_compressor
from coldstore.core.system import check_decompression_requirements
from coldstore.logger import (
    log_error,
    log_info,
    log_success,
    show_header,
    show_summary,
)


def main(
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
    no_check: Annotated[
        bool,
        typer.Option(
            "--no-check", help="Skip integrity verification during extraction"
        ),
    ] = False,
):
    """Extract archives.

    Performs two-stage extraction:
    1. zstd decompression (with automatic window_log detection)
    2. tar extraction

    Includes safe directory creation with overwrite protection.

    Equivalent to extract-archive.sh functionality.
    """
    show_header("Cold Storage Standard - Extract", f"Extracting: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Output directory: {output_dir}")
    log_info(f"Force overwrite: {'enabled' if force else 'disabled'}")
    log_info(f"Integrity check: {'disabled' if no_check else 'enabled'}")

    # Step 1: Validate archive file
    if not archive_path.name.endswith(".tar.zst"):
        log_error("Archive file must have .tar.zst extension")
        raise typer.Exit(1)

    # Step 2: Get archive information
    compressor = create_compressor()
    archive_info = compressor.get_archive_info(archive_path)

    log_info(f"Archive size: {archive_info['compressed_size'] / (1024 * 1024):.1f} MB")
    log_info(f"Memory required: ~{archive_info['memory_required_mb']} MB")
    log_info(f"Window log: {archive_info['window_log']}")

    # Step 3: System requirements check
    log_info("Checking system requirements...")
    if not check_decompression_requirements(
        archive_path,
        output_dir,
        required_memory_mb=archive_info["memory_required_mb"],
        show_info=False,
    ):
        log_error("System requirements check failed")
        raise typer.Exit(1)

    # Step 4: Prepare output directory
    base_name = archive_path.stem.replace(".tar", "")  # Remove .tar.zst -> .tar
    extract_dir = output_dir / base_name

    # Check if output directory exists
    if (
        extract_dir.exists() and not force and any(extract_dir.iterdir())
    ):  # Check if directory is not empty
        log_error(f"Output directory already exists and is not empty: {extract_dir}")
        log_info("Use --force to overwrite existing files")
        raise typer.Exit(1)

    # Create output directory
    extract_dir.mkdir(parents=True, exist_ok=True)
    log_info(f"Extracting to: {extract_dir}")

    # Step 5: Perform extraction
    try:
        success = compressor.decompress_archive(
            archive_path, extract_dir, enable_check=not no_check
        )

        if not success:
            log_error("Extraction failed")
            raise typer.Exit(1)

    except Exception as e:
        log_error(f"Extraction failed: {e}")
        raise typer.Exit(1) from e

    # Step 6: Show completion summary
    try:
        # Count extracted files
        extracted_files = list(extract_dir.rglob("*"))
        file_count = len([f for f in extracted_files if f.is_file()])
        dir_count = len([f for f in extracted_files if f.is_dir()])

        # Calculate extracted size
        extracted_size = sum(f.stat().st_size for f in extracted_files if f.is_file())

        show_summary(
            "Cold Storage Extraction Complete",
            [
                f"Archive: {archive_path.name}",
                f"Extracted {file_count} files and {dir_count} directories",
                f"Total size: {extracted_size / (1024 * 1024):.1f} MB",
                f"Output location: {extract_dir}",
                f"Memory used: ~{archive_info['memory_required_mb']} MB",
            ],
        )

        log_success("Archive extraction completed successfully!")

    except Exception as e:
        log_error(f"Failed to calculate extraction statistics: {e}")
        log_success("Archive extraction completed successfully!")  # Still show success
