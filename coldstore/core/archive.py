"""Archive handling with unified multi-format support."""

from pathlib import Path

from coldstore.core.format_detector import ArchiveFormat, create_format_detector
from coldstore.core.handlers import ArchiveEntry, BaseArchiveHandler, create_handler
from coldstore.logger import log_detail, log_error, log_info, log_step, log_warning


class ArchiveAnalyzer:
    """Unified archive analyzer supporting multiple formats."""

    def __init__(self):
        self.format_detector = create_format_detector()
        self.handler: BaseArchiveHandler | None = None
        self.temp_dir: Path | None = None
        self.detected_format: ArchiveFormat | None = None
        self._cleanup_initialized = False

    def _ensure_cleanup_initialized(self):
        """Ensure cleanup system is initialized (called lazily)."""
        if not self._cleanup_initialized:
            from coldstore.core.cleanup import initialize_cleanup

            initialize_cleanup()
            self._cleanup_initialized = True

    def is_supported_archive(self, file_path: Path) -> bool:
        """Check if file is a supported archive format."""
        return self.format_detector.is_supported(file_path)

    def analyze_archive_structure(self, archive_path: Path) -> dict[str, any]:
        """Analyze archive structure using appropriate handler."""
        try:
            log_step(f"Analyzing archive structure: {archive_path.name}")

            # Detect format
            self.detected_format = self.format_detector.detect_format(archive_path)
            if self.detected_format == ArchiveFormat.UNKNOWN:
                log_error(f"Unsupported archive format: {archive_path}")
                return self._create_error_structure("Unsupported format")

            # Special validation for RAR format
            if (
                self.detected_format == ArchiveFormat.RAR
                and not self._validate_rar_processing()
            ):
                return self._create_error_structure("RAR processing not available")

            # Create appropriate handler
            self.handler = create_handler(archive_path, self.detected_format.value)
            if not self.handler:
                log_error(
                    f"No handler available for format: {self.detected_format.value}"
                )
                return self._create_error_structure("No handler available")

            # List archive contents
            entries = self.handler.list_contents()
            if not entries:
                log_warning("Archive appears to be empty")
                return self._create_empty_structure()

            # Analyze structure
            structure_info = self._analyze_structure(entries)
            log_info(f"Archive analysis complete: {len(entries)} entries")
            log_detail(f"Format: {self.detected_format.value}")
            log_detail(f"Structure: {structure_info['description']}")

            return structure_info

        except Exception as e:
            log_error(f"Failed to analyze archive: {e}")
            return self._create_error_structure(f"Analysis failed: {e}")

    def _validate_rar_processing(self) -> bool:
        """Validate RAR processing requirements before proceeding."""
        from coldstore.core.system_tools import validate_rar_requirements

        return validate_rar_requirements()

    def _create_error_structure(self, error_msg: str) -> dict[str, any]:
        """Create error structure info."""
        return {
            "type": "error",
            "description": error_msg,
            "has_single_root": False,
            "root_folder": None,
            "entries": [],
            "format": self.detected_format.value if self.detected_format else "unknown",
        }

    def _create_empty_structure(self) -> dict[str, any]:
        """Create empty structure info."""
        return {
            "type": "empty",
            "description": "Empty archive",
            "has_single_root": False,
            "root_folder": None,
            "entries": [],
            "format": self.detected_format.value if self.detected_format else "unknown",
        }

    def _analyze_structure(self, entries: list[ArchiveEntry]) -> dict[str, any]:
        """Analyze archive structure to determine organization."""
        if not entries:
            return self._create_empty_structure()

        # Convert ArchiveEntry objects to compatible format
        entry_dicts = []
        for entry in entries:
            entry_dict = {
                "path": entry.path,
                "size": entry.size,
                "is_dir": entry.is_dir,
                "compressed_size": entry.compressed_size,
            }
            entry_dicts.append(entry_dict)

        # Get all top-level entries
        top_level_entries = []
        for entry in entry_dicts:
            path_parts = entry["path"].split("/")
            # Handle different path separators and formats
            if len(path_parts) == 1 or (len(path_parts) == 2 and path_parts[1] == ""):
                top_level_entries.append(entry)

        # Check for single root folder structure
        if len(top_level_entries) == 1 and top_level_entries[0]["is_dir"]:
            return {
                "type": "single_root",
                "description": f"Single root folder: {top_level_entries[0]['path']}",
                "has_single_root": True,
                "root_folder": top_level_entries[0]["path"],
                "entries": entry_dicts,
                "format": self.detected_format.value
                if self.detected_format
                else "unknown",
            }

        # Check for multiple top-level entries
        if len(top_level_entries) > 1:
            dirs = sum(1 for e in top_level_entries if e["is_dir"])
            files = len(top_level_entries) - dirs
            return {
                "type": "multiple_roots",
                "description": f"Multiple top-level entries: {dirs} dirs, {files} files",
                "has_single_root": False,
                "root_folder": None,
                "entries": entry_dicts,
                "format": self.detected_format.value
                if self.detected_format
                else "unknown",
            }

        # Single file at root
        if top_level_entries:
            return {
                "type": "single_file",
                "description": f"Single file: {top_level_entries[0]['path']}",
                "has_single_root": False,
                "root_folder": None,
                "entries": entry_dicts,
                "format": self.detected_format.value
                if self.detected_format
                else "unknown",
            }

        # Fallback case
        return {
            "type": "unknown",
            "description": "Unknown structure",
            "has_single_root": False,
            "root_folder": None,
            "entries": entry_dicts,
            "format": self.detected_format.value if self.detected_format else "unknown",
        }

    def extract_archive(self, archive_path: Path, extract_to: Path) -> bool:
        """Extract archive using appropriate handler."""
        try:
            log_step(f"Extracting archive: {archive_path.name}")

            # Detect format if not already done
            if not self.handler:
                detected_format = self.format_detector.detect_format(archive_path)
                if detected_format == ArchiveFormat.UNKNOWN:
                    log_error(f"Unsupported archive format: {archive_path}")
                    return False

                # Special validation for RAR format
                if (
                    detected_format == ArchiveFormat.RAR
                    and not self._validate_rar_processing()
                ):
                    return False

                self.handler = create_handler(archive_path, detected_format.value)
                if not self.handler:
                    log_error(
                        f"No handler available for format: {detected_format.value}"
                    )
                    return False

            # Extract using the handler
            success = self.handler.extract_all(extract_to)
            if success:
                log_info(f"Archive extracted successfully to: {extract_to}")
                log_detail(f"Format: {self.handler.format_name}")
                log_detail("✅ Multi-format extraction successful")
            else:
                # For RAR format, the handler already provides detailed error messages
                if self.handler.format_name != "rar":
                    log_error("Archive extraction failed")

            return success

        except Exception as e:
            log_error(f"Failed to extract archive: {e}")
            log_detail(f"Error details: {str(e)}")
            return False

    def handle_nested_structure(
        self, extracted_path: Path, structure_info: dict[str, any]
    ) -> Path:
        """Handle nested folder structures by flattening if needed."""
        if not structure_info["has_single_root"]:
            return extracted_path

        root_folder = structure_info["root_folder"]
        if not root_folder:
            return extracted_path

        root_path = extracted_path / root_folder

        if root_path.exists() and root_path.is_dir():
            log_info(f"Detected single root folder: {root_folder}")

            # Check if we should flatten (avoid double nesting)
            try:
                contents = list(root_path.iterdir())
                if len(contents) > 1 or (len(contents) == 1 and contents[0].is_file()):
                    log_info("Flattening single root folder structure")
                    return root_path
            except Exception as e:
                log_warning(f"Error checking root folder contents: {e}")

        return extracted_path

    def prepare_extraction_temp(self) -> Path:
        """Create temporary directory for extraction."""
        if self.temp_dir is None:
            self._ensure_cleanup_initialized()
            from coldstore.core.cleanup import create_managed_temp_dir

            self.temp_dir = create_managed_temp_dir(prefix="coldstore_extract_")
        return self.temp_dir

    def cleanup_temp(self):
        """Clean up temporary extraction directory with enhanced error handling."""
        # Check if global cleanup is already in progress
        from coldstore.core.cleanup import get_cleanup_manager

        cleanup_manager = get_cleanup_manager()
        with cleanup_manager._lock:
            if cleanup_manager._cleanup_in_progress:
                # Global cleanup is already handling this, skip to avoid conflict
                log_detail(
                    "Skipping analyzer cleanup - global cleanup already in progress"
                )
                return

        if self.temp_dir and self.temp_dir.exists():
            from coldstore.core.cleanup import _force_remove_directory

            try:
                # Use the enhanced cleanup system with increased retries
                if _force_remove_directory(self.temp_dir, max_retries=5):
                    log_info("Temporary extraction directory cleaned up successfully")
                    # Remove from cleanup manager since we cleaned it manually
                    get_cleanup_manager().remove_temp_directory(self.temp_dir)
                else:
                    log_warning(f"Failed to cleanup temp directory: {self.temp_dir}")
                    log_detail(
                        "Directory will be cleaned up on next startup or system restart"
                    )
            except Exception as e:
                log_warning(f"Failed to cleanup temp directory: {e}")
                log_detail(
                    "Directory will be cleaned up on next startup or system restart"
                )
            finally:
                self.temp_dir = None

    def get_archive_info(self, archive_path: Path) -> dict[str, any]:
        """Get comprehensive archive information using appropriate handler."""
        try:
            # Detect format if not already done
            if not self.handler:
                detected_format = self.format_detector.detect_format(archive_path)
                if detected_format == ArchiveFormat.UNKNOWN:
                    log_warning(f"Unsupported archive format: {archive_path}")
                    return {
                        "files": 0,
                        "folders": 0,
                        "total_size": 0,
                        "compressed_size": archive_path.stat().st_size,
                        "format": "unknown",
                    }

                self.handler = create_handler(archive_path, detected_format.value)
                if not self.handler:
                    log_warning(
                        f"No handler available for format: {detected_format.value}"
                    )
                    return {
                        "files": 0,
                        "folders": 0,
                        "total_size": 0,
                        "compressed_size": archive_path.stat().st_size,
                        "format": detected_format.value,
                    }

            # Get info using the handler
            return self.handler.get_archive_info()

        except Exception as e:
            log_warning(f"Failed to get archive info: {e}")
            return {
                "files": 0,
                "folders": 0,
                "total_size": 0,
                "compressed_size": archive_path.stat().st_size,
                "format": "unknown",
            }

    def get_format_info(self, archive_path: Path) -> dict[str, any]:
        """Get format detection information."""
        return self.format_detector.get_format_info(archive_path)

    def list_supported_formats(self) -> list[str]:
        """List all supported archive formats."""
        return [fmt.value for fmt in ArchiveFormat if fmt != ArchiveFormat.UNKNOWN]


def create_analyzer() -> ArchiveAnalyzer:
    """Create an archive analyzer instance."""
    return ArchiveAnalyzer()
