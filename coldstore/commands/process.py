"""Process command - Verify and extract archives."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.commands.verify import show_verification_results, verify_single_archive
from coldstore.core.compress import create_compressor
from coldstore.core.system import check_decompression_requirements
from coldstore.logging import (
    log_error,
    log_info,
    log_success,
    log_warning,
    show_header,
    show_summary,
)


def main(
    archive_path: Annotated[
        Path,
        typer.Argument(
            help="Archive file to process",
            exists=True,
            readable=True,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Output directory for extracted files"),
    ] = Path.cwd(),
    verify_only: Annotated[
        bool, typer.Option("--verify-only", help="Only verify archive, don't extract")
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force extraction even if directory exists"),
    ] = False,
    no_check: Annotated[
        bool,
        typer.Option(
            "--no-check", help="Skip integrity verification before extraction"
        ),
    ] = False,
):
    """Verify and extract archives.

    Combines verify and extract operations:
    1. Performs multi-layer integrity verification
    2. Extracts archive if verification passes (unless --verify-only)

    Equivalent to verify-and-extract.sh functionality.
    """
    show_header("Cold Storage Standard - Process", f"Processing: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Output directory: {output_dir}")
    log_info(f"Mode: {'verify only' if verify_only else 'verify and extract'}")
    log_info(f"Force overwrite: {'enabled' if force else 'disabled'}")
    log_info(f"Integrity check: {'disabled' if no_check else 'enabled'}")

    # Step 1: Validate archive file
    if not archive_path.name.endswith(".tar.zst"):
        log_error("Archive file must have .tar.zst extension")
        raise typer.Exit(1)

    # Step 2: Get archive information
    compressor = create_compressor()
    archive_info = compressor.get_archive_info(archive_path)

    log_info(f"Archive size: {archive_info['compressed_size'] / (1024*1024):.1f} MB")
    log_info(f"Memory required: ~{archive_info['memory_required_mb']} MB")
    log_info(f"Window log: {archive_info['window_log']}")

    # Step 3: System requirements check
    if not verify_only:
        log_info("Checking system requirements...")
        if not check_decompression_requirements(
            archive_path,
            output_dir,
            required_memory_mb=archive_info["memory_required_mb"],
            show_info=False,
        ):
            log_error("System requirements check failed")
            raise typer.Exit(1)

    # Step 4: Verification phase
    verification_passed = True

    if not no_check:
        log_info("Starting integrity verification...")

        try:
            verification_results = verify_single_archive(archive_path)

            # Show verification results
            show_verification_results({archive_path.name: verification_results})

            # Check if verification passed
            has_failures = any(r is False for r in verification_results.values())

            if has_failures:
                log_error("Archive integrity verification failed")
                verification_passed = False
            else:
                log_success("Archive integrity verification passed")

        except Exception as e:
            log_error(f"Verification failed: {e}")
            verification_passed = False
    else:
        log_warning("Integrity verification skipped (--no-check enabled)")

    # Step 5: Early exit if verify-only or verification failed
    if verify_only:
        if verification_passed:
            log_success("Verification completed successfully")
            return
        else:
            log_error("Verification failed")
            raise typer.Exit(1)

    if not verification_passed and not no_check:
        log_error("Cannot proceed with extraction due to verification failures")
        log_info("Use --no-check to force extraction (not recommended)")
        raise typer.Exit(1)

    # Step 6: Extraction phase
    log_info("Starting extraction...")

    # Prepare output directory
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

    # Perform extraction
    try:
        # Note: We disable integrity checks during extraction since we already verified
        success = compressor.decompress_archive(
            archive_path,
            extract_dir,
            enable_check=False,  # Already verified above
        )

        if not success:
            log_error("Extraction failed")
            raise typer.Exit(1)

    except Exception as e:
        log_error(f"Extraction failed: {e}")
        raise typer.Exit(1) from e

    # Step 7: Show completion summary
    try:
        # Count extracted files
        extracted_files = list(extract_dir.rglob("*"))
        file_count = len([f for f in extracted_files if f.is_file()])
        dir_count = len([f for f in extracted_files if f.is_dir()])

        # Calculate extracted size
        extracted_size = sum(f.stat().st_size for f in extracted_files if f.is_file())

        show_summary(
            "Cold Storage Processing Complete",
            [
                f"Archive: {archive_path.name}",
                f"Verification: {'PASSED' if verification_passed else 'SKIPPED'}",
                f"Extracted {file_count} files and {dir_count} directories",
                f"Total size: {extracted_size / (1024*1024):.1f} MB",
                f"Output location: {extract_dir}",
                f"Memory used: ~{archive_info['memory_required_mb']} MB",
            ],
        )

        log_success("Archive processing completed successfully!")

    except Exception as e:
        log_error(f"Failed to calculate processing statistics: {e}")
        log_success("Archive processing completed successfully!")  # Still show success
