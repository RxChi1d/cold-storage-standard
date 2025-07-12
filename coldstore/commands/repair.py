"""Repair command - Repair corrupted archives using PAR2."""

from pathlib import Path
from typing import Annotated

import typer

# PAR2 functionality is now handled directly by the PAR2Engine class
# PAR2 system tools are now handled by the PAR2Engine class
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

    # Step 1: Initialize PAR2 engine
    try:
        from coldstore.core.par2 import PAR2Engine

        par2_engine = PAR2Engine()
        log_info(f"Using PAR2 tool: {par2_engine.get_version()}")
    except Exception as e:
        log_error(f"PAR2 initialization failed: {e}")
        raise typer.Exit(1) from None

    # Step 2: Determine PAR2 file path
    par2_file = None
    if archive_path.name.endswith(".par2"):
        # User provided PAR2 file directly
        par2_file = archive_path
    else:
        # Look for corresponding PAR2 file
        if archive_path.name.endswith(".tar.zst"):
            par2_file = archive_path.parent / f"{archive_path.name}.par2"
        else:
            par2_file = archive_path.parent / f"{archive_path.name}.par2"

    # Step 3: Check if PAR2 file exists
    if not par2_file.exists():
        log_error(f"PAR2 file not found: {par2_file}")
        log_info("PAR2 files are required for repair functionality")
        log_info("Generate PAR2 files using: coldstore pack <archive>")
        raise typer.Exit(1)

    log_info(f"Using PAR2 file: {par2_file}")

    # Step 4: Check PAR2 file information
    log_info("Analyzing PAR2 file structure...")

    # Step 5: Verify PAR2 integrity
    log_info("Verifying PAR2 integrity...")
    verification_result = par2_engine.verify_par2(str(par2_file))

    if verification_result["success"]:
        log_success("PAR2 verification passed - no repair needed")

        # Show verification results
        if verification_result["files_verified"] > 0:
            log_info(f"Verified files: {verification_result['files_verified']}")

        if verify_only:
            show_summary(
                "PAR2 Verification Complete",
                [
                    f"PAR2 file: {par2_file.name}",
                    f"Files verified: {verification_result['files_verified']}",
                    "Status: All files OK",
                    "Repair: Not needed",
                ],
            )
            log_success("All files verified successfully!")
            return
        else:
            log_info("No repair needed - all files are intact")
            return

    # Step 6: Handle verification failure
    log_warning("PAR2 verification failed - repair may be needed")

    # Show detailed verification results
    if verification_result["files_missing"] > 0:
        log_error(f"Missing files: {verification_result['files_missing']}")

    if verification_result["files_damaged"] > 0:
        log_error(f"Damaged files: {verification_result['files_damaged']}")

    if verify_only:
        show_summary(
            "PAR2 Verification Complete",
            [
                f"PAR2 file: {par2_file.name}",
                f"Files verified: {verification_result.get('files_verified', 0)}",
                f"Files missing: {verification_result.get('files_missing', 0)}",
                f"Files damaged: {verification_result.get('files_damaged', 0)}",
                "Status: Repair needed",
            ],
        )
        log_error("Verification failed - repair required")
        raise typer.Exit(1)

    # Step 7: Attempt repair
    if not verification_result.get("repairable", True):
        log_error("PAR2 indicates repair is not possible")
        log_info("The archive may be too damaged to repair")
        raise typer.Exit(1)

    log_info("Attempting PAR2 repair...")
    repair_result = par2_engine.repair_files(str(par2_file))

    # Step 8: Handle repair results
    if repair_result["success"]:
        log_success("PAR2 repair completed successfully!")

        # Show repair results
        if repair_result["files_repaired"] > 0:
            log_info(f"Repaired files: {repair_result['files_repaired']}")

        # Final verification
        log_info("Performing final verification...")
        final_verification = par2_engine.verify_par2(str(par2_file))

        if final_verification["success"]:
            show_summary(
                "PAR2 Repair Complete",
                [
                    f"PAR2 file: {par2_file.name}",
                    f"Files repaired: {repair_result.get('files_repaired', 0)}",
                    "Final verification: PASSED",
                    "Status: Successfully repaired",
                ],
            )
            log_success("Archive repair completed successfully!")
        else:
            log_warning("Repair completed but final verification failed")
            show_summary(
                "PAR2 Repair Complete",
                [
                    f"PAR2 file: {par2_file.name}",
                    f"Files repaired: {repair_result.get('files_repaired', 0)}",
                    "Final verification: FAILED",
                    "Status: Repair may be incomplete",
                ],
            )
            log_error("Repair may not be complete - manual verification recommended")
            raise typer.Exit(1)

    else:
        log_error("PAR2 repair failed")

        if not repair_result.get("repair_possible", True):
            log_error("Repair not possible - insufficient recovery data")
            log_info("The archive may be too damaged to repair")
            log_info("You may need to restore from a different backup")

        show_summary(
            "PAR2 Repair Failed",
            [
                f"PAR2 file: {par2_file.name}",
                f"Files missing: {verification_result.get('files_missing', 0)}",
                f"Files damaged: {verification_result.get('files_damaged', 0)}",
                "Status: Repair failed",
                "Recommendation: Restore from backup",
            ],
        )

        raise typer.Exit(1)
