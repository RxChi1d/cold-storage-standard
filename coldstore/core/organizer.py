"""File organization system for Cold Storage Standard."""

import os
from pathlib import Path

from coldstore.logger import log_detail, log_info, log_step, log_warning


class FileOrganizer:
    """File organization system matching bash script functionality."""

    def __init__(self, output_dir: Path, flat_mode: bool = False):
        self.output_dir = Path(output_dir)
        self.flat_mode = flat_mode
        self.base_name = ""
        self.output_files: dict[str, Path] = {}

    def setup_output_path(self, input_path: Path) -> Path:
        """Set up output path based on input and mode."""
        # Generate base name from input path
        if input_path.is_file():
            # For files, use filename without extension
            self.base_name = input_path.stem
            # Remove common archive extensions
            for ext in [".7z", ".zip", ".rar", ".tar", ".gz", ".bz2", ".xz"]:
                if self.base_name.endswith(ext.replace(".", "")):
                    self.base_name = self.base_name[: -len(ext) + 1]
                    break
        else:
            # For directories, use directory name
            self.base_name = input_path.name

        if self.flat_mode:
            # Flat mode: output directly to current directory
            output_path = Path.cwd()
        else:
            # Organized mode: create subdirectory
            output_path = self.output_dir / self.base_name
            output_path.mkdir(parents=True, exist_ok=True)

        # Define all output files
        self.output_files = {
            "archive": output_path / f"{self.base_name}.tar.zst",
            "sha256": output_path / f"{self.base_name}.tar.zst.sha256",
            "blake3": output_path / f"{self.base_name}.tar.zst.blake3",
            "par2": output_path / f"{self.base_name}.tar.zst.par2",
        }

        log_info(f"Output mode: {'flat' if self.flat_mode else 'organized'}")
        log_info(f"Base name: {self.base_name}")
        log_info(f"Output directory: {output_path}")

        return output_path

    def check_existing_files(self) -> bool:
        """Check if output files already exist."""
        existing_files = []
        for file_type, file_path in self.output_files.items():
            if file_path.exists():
                existing_files.append(f"{file_type}: {file_path}")

        if existing_files:
            log_warning("Existing files found:")
            for file_info in existing_files:
                log_detail(file_info)
            return True

        return False

    def create_directory_structure(self) -> bool:
        """Create necessary directory structure."""
        try:
            for file_path in self.output_files.values():
                file_path.parent.mkdir(parents=True, exist_ok=True)

            log_info("Directory structure created successfully")
            return True
        except OSError as e:
            log_warning(f"Failed to create directory structure: {e}")
            return False

    def get_output_file(self, file_type: str) -> Path | None:
        """Get output file path by type."""
        return self.output_files.get(file_type)

    def get_all_output_files(self) -> dict[str, Path]:
        """Get all output file paths."""
        return self.output_files.copy()

    def cleanup_partial_files(self, keep_types: list[str] | None = None):
        """Clean up partial files after failed operations with enhanced error handling."""
        if keep_types is None:
            keep_types = []

        cleaned_files = []
        failed_files = []

        for file_type, file_path in self.output_files.items():
            if file_type not in keep_types and file_path.exists():
                try:
                    # Use enhanced cleanup system for better Windows compatibility
                    from coldstore.core.cleanup import _force_remove_file

                    if _force_remove_file(file_path, max_retries=5):
                        cleaned_files.append(file_path.name)
                    else:
                        failed_files.append(file_path.name)
                        log_warning(f"Failed to remove {file_path}")
                except Exception as e:
                    failed_files.append(file_path.name)
                    log_warning(f"Failed to remove {file_path}: {e}")

        if cleaned_files:
            log_info(f"Cleaned up partial files: {', '.join(cleaned_files)}")

        if failed_files:
            log_warning(
                f"Failed to clean up {len(failed_files)} files: {', '.join(failed_files)}"
            )
            log_detail(
                "These files will be cleaned up on next startup or system restart"
            )

    def validate_output_permissions(self) -> bool:
        """Validate write permissions for output files."""
        for file_type, file_path in self.output_files.items():
            parent_dir = file_path.parent
            if not os.access(parent_dir, os.W_OK):
                log_warning(f"No write permission for {file_type} output: {parent_dir}")
                return False

        log_info("Output permissions validated")
        return True

    def get_size_info(self) -> dict[str, int]:
        """Get size information for existing output files."""
        sizes = {}
        for file_type, file_path in self.output_files.items():
            if file_path.exists():
                sizes[file_type] = file_path.stat().st_size
            else:
                sizes[file_type] = 0
        return sizes

    def show_output_summary(self):
        """Show summary of output files and their status."""
        # Import here to avoid circular imports
        from coldstore.logger import _should_show_detail

        if not _should_show_detail():
            return

        log_step("Output file summary:")

        for file_type, file_path in self.output_files.items():
            status = "exists" if file_path.exists() else "to be created"
            size_info = ""
            if file_path.exists():
                size_mb = file_path.stat().st_size / (1024 * 1024)
                size_info = f" ({size_mb:.1f} MB)"

            log_detail(
                f"{file_type.capitalize()}: {file_path.name} - {status}{size_info}"
            )


def create_organizer(
    output_dir: Path,
    flat_mode: bool = False,
) -> FileOrganizer:
    """Create a file organizer instance."""
    return FileOrganizer(output_dir, flat_mode)
