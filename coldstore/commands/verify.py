"""Verify command - Verify archive integrity."""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from coldstore.core.compress import create_compressor
from coldstore.core.hash import create_hash_generator
from coldstore.logging import (
    console,
    log_error,
    log_info,
    log_success,
    show_header,
    show_summary,
)


def verify_single_archive(archive_path: Path, verbose: bool = False) -> dict[str, bool]:
    """Verify a single archive file."""
    log_info(f"Verifying archive: {archive_path.name}")

    results = {
        "zstd_integrity": False,
        "sha256_hash": None,
        "blake3_hash": None,
        "tar_integrity": False,
    }

    # Step 1: Verify zstd integrity
    compressor = create_compressor()
    try:
        results["zstd_integrity"] = compressor.verify_zstd_integrity(archive_path)
    except Exception as e:
        log_error(f"Zstd integrity check failed: {e}")
        results["zstd_integrity"] = False

    # Step 2: Verify hash files
    hash_generator = create_hash_generator()
    try:
        hash_results = hash_generator.verify_all_hashes(archive_path)
        results["sha256_hash"] = hash_results.get("sha256")
        results["blake3_hash"] = hash_results.get("blake3")
    except Exception as e:
        log_error(f"Hash verification failed: {e}")
        results["sha256_hash"] = False
        results["blake3_hash"] = False

    # Step 3: Verify tar integrity (through decompression test)
    try:
        # Create a temporary tar file to test decompression
        temp_tar = compressor.create_temp_tar(prefix="verify_")

        # Test decompression (this will verify tar integrity)
        if compressor.decompress_with_zstd(archive_path, temp_tar):
            results["tar_integrity"] = compressor.verify_tar_integrity(temp_tar)
        else:
            results["tar_integrity"] = False

        # Clean up
        compressor.cleanup_temp_tar()

    except Exception as e:
        log_error(f"Tar integrity check failed: {e}")
        results["tar_integrity"] = False

    return results


def show_verification_results(
    results: dict[str, dict[str, bool]], verbose: bool = False
):
    """Display verification results in a table."""
    table = Table(title="Archive Verification Results")
    table.add_column("Archive", style="cyan")
    table.add_column("Zstd", style="white")
    table.add_column("SHA-256", style="white")
    table.add_column("BLAKE3", style="white")
    table.add_column("Tar", style="white")
    table.add_column("Overall", style="white")

    for archive_name, result in results.items():
        # Determine overall result
        passed_checks = []
        failed_checks = []
        missing_checks = []

        for check_name, check_result in result.items():
            if check_result is True:
                passed_checks.append(check_name)
            elif check_result is False:
                failed_checks.append(check_name)
            else:  # None means check was skipped or file not found
                missing_checks.append(check_name)

        # Overall status
        if failed_checks:
            overall_status = "[red]FAILED[/red]"
        elif missing_checks and not passed_checks:
            overall_status = "[yellow]INCOMPLETE[/yellow]"
        elif passed_checks:
            overall_status = "[green]PASSED[/green]"
        else:
            overall_status = "[red]UNKNOWN[/red]"

        # Individual check results
        def format_result(check_result):
            if check_result is True:
                return "[green]✓[/green]"
            elif check_result is False:
                return "[red]✗[/red]"
            else:
                return "[yellow]—[/yellow]"

        table.add_row(
            archive_name,
            format_result(result["zstd_integrity"]),
            format_result(result["sha256_hash"]),
            format_result(result["blake3_hash"]),
            format_result(result["tar_integrity"]),
            overall_status,
        )

    console.print(table)


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

    Performs multi-layer verification:
    1. zstd integrity check (with automatic window_log detection)
    2. SHA-256 hash verification
    3. BLAKE3 hash verification
    4. tar content verification

    Equivalent to verify-archive.sh functionality.
    """
    show_header("Cold Storage Standard - Verify", f"Verifying: {archive_path}")

    log_info(f"Archive: {archive_path}")
    log_info(f"Mode: {'directory batch' if directory else 'single file'}")
    log_info(f"Verbose: {'enabled' if verbose else 'disabled'}")

    results = {}

    if directory:
        # Batch verification
        if not archive_path.is_dir():
            log_error("Specified path is not a directory")
            raise typer.Exit(1)

        # Find all .tar.zst files
        archive_files = list(archive_path.rglob("*.tar.zst"))

        if not archive_files:
            log_error("No .tar.zst files found in directory")
            raise typer.Exit(1)

        log_info(f"Found {len(archive_files)} archive files")

        # Verify each archive
        for archive_file in archive_files:
            try:
                file_results = verify_single_archive(archive_file, verbose)
                results[archive_file.name] = file_results
            except Exception as e:
                log_error(f"Failed to verify {archive_file.name}: {e}")
                results[archive_file.name] = {
                    "zstd_integrity": False,
                    "sha256_hash": False,
                    "blake3_hash": False,
                    "tar_integrity": False,
                }
    else:
        # Single file verification
        if not archive_path.name.endswith(".tar.zst"):
            log_error("Archive file must have .tar.zst extension")
            raise typer.Exit(1)

        try:
            file_results = verify_single_archive(archive_path, verbose)
            results[archive_path.name] = file_results
        except Exception as e:
            log_error(f"Failed to verify {archive_path.name}: {e}")
            results[archive_path.name] = {
                "zstd_integrity": False,
                "sha256_hash": False,
                "blake3_hash": False,
                "tar_integrity": False,
            }

    # Display results
    if not quiet:
        show_verification_results(results, verbose)

    # Calculate summary statistics
    total_archives = len(results)
    passed_archives = 0
    failed_archives = 0

    for _archive_name, result in results.items():
        has_failures = any(r is False for r in result.values())
        if has_failures:
            failed_archives += 1
        else:
            passed_archives += 1

    # Show summary
    if not quiet:
        show_summary(
            "Cold Storage Verification Complete",
            [
                f"Total archives: {total_archives}",
                f"Passed: {passed_archives}",
                f"Failed: {failed_archives}",
                f"Success rate: {(passed_archives/total_archives)*100:.1f}%"
                if total_archives > 0
                else "N/A",
            ],
        )

    if failed_archives > 0:
        log_error(f"Verification failed for {failed_archives} archive(s)")
        raise typer.Exit(1)
    else:
        log_success("All archives verified successfully!")
