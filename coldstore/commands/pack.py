"""Pack command - Convert archives to cold storage format."""

from pathlib import Path
from typing import Annotated

import typer

from coldstore.core.archive import create_analyzer
from coldstore.core.compress import create_compressor
from coldstore.core.hash import create_hash_generator
from coldstore.core.organizer import create_organizer
from coldstore.core.progress import create_progress_manager
from coldstore.core.system import check_system_requirements
from coldstore.logging import (
    log_error,
    log_info,
    log_success,
    show_header,
    show_summary,
)


def main(
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

    This command processes multiple archive formats and converts them to verified
    tar.zst archives with SHA-256, BLAKE3, and PAR2 protection.

    Supported formats:
    - 7z archives (.7z)
    - ZIP archives (.zip)
    - RAR archives (.rar)
    - TAR archives (.tar, .tar.gz, .tar.bz2, .tar.xz)
    - Standalone compressed files (.gz, .bz2, .xz)

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

    # Step 1: System requirements check
    log_info("Checking system requirements...")
    if not check_system_requirements(input_path, output_dir, not no_long, True):
        log_error("System requirements check failed")
        raise typer.Exit(1)

    # Step 2: Set up file organization
    organizer = create_organizer(output_dir, flat)
    organizer.setup_output_path(input_path)

    # Check for existing files
    if organizer.check_existing_files():
        log_error(
            "Output files already exist. Remove them or use a different output directory."
        )
        raise typer.Exit(1)

    # Step 3: Handle archive extraction if needed
    analyzer = create_analyzer()
    work_path = input_path

    if input_path.is_file():
        # Check if it's a supported archive format
        if analyzer.is_supported_archive(input_path):
            format_info = analyzer.get_format_info(input_path)
            log_info(
                f"Detected {format_info['format']} archive file, analyzing structure..."
            )

            structure_info = analyzer.analyze_archive_structure(input_path)

            # Check for analysis errors
            if structure_info.get("type") == "error":
                log_error(f"Archive analysis failed: {structure_info['description']}")
                raise typer.Exit(1)

            # Extract to temporary directory
            temp_extract_path = analyzer.prepare_extraction_temp()
            if not analyzer.extract_archive(input_path, temp_extract_path):
                log_error("Failed to extract archive")
                analyzer.cleanup_temp()
                raise typer.Exit(1)

            # Handle nested structures
            work_path = analyzer.handle_nested_structure(
                temp_extract_path, structure_info
            )
        else:
            # Check if it's a file we can't handle
            format_info = analyzer.get_format_info(input_path)
            if not format_info["supported"]:
                log_error(f"Unsupported archive format: {format_info['format']}")
                log_info(
                    "Supported formats: " + ", ".join(analyzer.list_supported_formats())
                )
                raise typer.Exit(1)

            # If it's not an archive, treat as a single file
            log_info("Processing single file (not an archive)")
            work_path = input_path

    try:
        # Step 4: Compression with progress tracking
        compressor = create_compressor()

        with create_progress_manager() as progress:
            progress.create_progress()

            # Add compression task
            progress.add_task("compression", "Compressing to tar.zst...", total=100)

            # Perform compression
            archive_path = organizer.get_output_file("archive")
            success = compressor.compress_directory(
                work_path,
                archive_path,
                level=level,
                threads=threads,
                long_mode=not no_long,
                enable_check=not no_check,
            )

            progress.complete_task("compression")

            if not success:
                log_error("Compression failed")
                organizer.cleanup_partial_files()
                raise typer.Exit(1)

        # Step 5: Generate integrity hashes
        if not no_check:
            hash_generator = create_hash_generator()
            if not hash_generator.generate_and_save_hashes(archive_path):
                log_error("Hash generation failed")
                organizer.cleanup_partial_files()
                raise typer.Exit(1)

        # Step 6: Show completion summary
        organizer.show_output_summary()

        # Calculate final statistics
        original_size = 0
        if input_path.is_file():
            original_size = input_path.stat().st_size
        else:
            original_size = sum(
                f.stat().st_size for f in input_path.rglob("*") if f.is_file()
            )

        compressed_size = archive_path.stat().st_size
        ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

        show_summary(
            "Cold Storage Conversion Complete",
            [
                f"Original size: {original_size / (1024 * 1024):.1f} MB",
                f"Compressed size: {compressed_size / (1024 * 1024):.1f} MB",
                f"Compression ratio: {ratio:.1f}%",
                f"Output location: {archive_path.parent}",
                f"Archive: {archive_path.name}",
                "Integrity files: SHA-256, BLAKE3"
                + ("" if no_check else ", PAR2 (planned)"),
            ],
        )

        log_success("Archive conversion completed successfully!")

    finally:
        # Cleanup temporary files
        if hasattr(analyzer, "cleanup_temp"):
            analyzer.cleanup_temp()
        if hasattr(compressor, "cleanup_temp_tar"):
            compressor.cleanup_temp_tar()
