"""Archive handling and 7z structure detection."""

import tempfile
from pathlib import Path

import py7zr

from coldstore.logging import log_detail, log_error, log_info, log_step, log_warning


class ArchiveAnalyzer:
    """Intelligent 7z structure detection and handling."""

    def __init__(self):
        # py7zr supports these formats natively
        self.supported_formats = [".7z", ".zip", ".tar", ".gz", ".bz2", ".xz"]
        # Note: .rar support is limited in py7zr, may need additional handling
        self.temp_dir: Path | None = None

    def is_supported_archive(self, file_path: Path) -> bool:
        """Check if file is a supported archive format."""
        return any(
            str(file_path).lower().endswith(ext) for ext in self.supported_formats
        )

    def analyze_archive_structure(self, archive_path: Path) -> dict:
        """Analyze archive structure to detect nested folders using py7zr."""
        try:
            log_step(f"Analyzing archive structure: {archive_path.name}")

            # Use py7zr to list archive contents
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                entries = self._extract_file_info_from_py7zr(archive)

            structure_info = self._analyze_structure(entries)

            log_info(f"Archive analysis complete: {len(entries)} entries")
            log_detail(f"Structure: {structure_info['description']}")

            return structure_info

        except Exception as e:
            log_error(f"Failed to analyze archive: {e}")
            return {
                "type": "unknown",
                "description": "Failed to analyze",
                "has_single_root": False,
                "root_folder": None,
                "entries": [],
            }

    def _extract_file_info_from_py7zr(self, archive: py7zr.SevenZipFile) -> list[dict]:
        """Extract file information from py7zr archive object."""
        entries = []

        try:
            # Get list of files in archive
            file_list = archive.list()

            for file_info in file_list:
                # py7zr FileInfo object contains filename, is_directory, etc.
                entry = {
                    "path": file_info.filename,
                    "size": file_info.uncompressed
                    if hasattr(file_info, "uncompressed")
                    else 0,
                    "is_dir": file_info.is_directory,
                    "attributes": "D" if file_info.is_directory else "A",
                }
                entries.append(entry)

        except Exception as e:
            log_warning(f"Error reading archive contents: {e}")

        return entries

    def _analyze_structure(self, entries: list[dict]) -> dict:
        """Analyze archive structure to determine organization."""
        if not entries:
            return {
                "type": "empty",
                "description": "Empty archive",
                "has_single_root": False,
                "root_folder": None,
                "entries": [],
            }

        # Get all top-level entries
        top_level_entries = []
        for entry in entries:
            path_parts = entry["path"].split("/")
            if len(path_parts) == 1 or (len(path_parts) == 2 and path_parts[1] == ""):
                top_level_entries.append(entry)

        # Check for single root folder structure
        if len(top_level_entries) == 1 and top_level_entries[0]["is_dir"]:
            return {
                "type": "single_root",
                "description": f"Single root folder: {top_level_entries[0]['path']}",
                "has_single_root": True,
                "root_folder": top_level_entries[0]["path"],
                "entries": entries,
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
                "entries": entries,
            }

        # Single file at root
        return {
            "type": "single_file",
            "description": f"Single file: {top_level_entries[0]['path']}",
            "has_single_root": False,
            "root_folder": None,
            "entries": entries,
        }

    def extract_archive(self, archive_path: Path, extract_to: Path) -> bool:
        """Extract archive to specified directory using py7zr."""
        try:
            log_step(f"Extracting archive: {archive_path.name}")

            # Create extraction directory
            extract_to.mkdir(parents=True, exist_ok=True)

            # Extract using py7zr
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                archive.extractall(path=extract_to)

            log_info(f"Archive extracted to: {extract_to}")
            log_detail("✅ Cross-platform extraction using py7zr")
            return True

        except Exception as e:
            log_error(f"Failed to extract archive: {e}")
            log_detail(f"Error details: {str(e)}")
            return False

    def handle_nested_structure(
        self, extracted_path: Path, structure_info: dict
    ) -> Path:
        """Handle nested folder structures by flattening if needed."""
        if not structure_info["has_single_root"]:
            return extracted_path

        root_folder = structure_info["root_folder"]
        root_path = extracted_path / root_folder

        if root_path.exists() and root_path.is_dir():
            log_info(f"Detected single root folder: {root_folder}")

            # Check if we should flatten (avoid double nesting)
            contents = list(root_path.iterdir())
            if len(contents) > 1 or (len(contents) == 1 and contents[0].is_file()):
                log_info("Flattening single root folder structure")
                return root_path

        return extracted_path

    def prepare_extraction_temp(self) -> Path:
        """Create temporary directory for extraction."""
        if self.temp_dir is None:
            self.temp_dir = Path(tempfile.mkdtemp(prefix="coldstore_"))
        return self.temp_dir

    def cleanup_temp(self):
        """Clean up temporary extraction directory."""
        if self.temp_dir and self.temp_dir.exists():
            import shutil

            shutil.rmtree(self.temp_dir)
            self.temp_dir = None
            log_info("Temporary extraction directory cleaned up")

    def get_archive_info(self, archive_path: Path) -> dict:
        """Get comprehensive archive information using py7zr."""
        try:
            with py7zr.SevenZipFile(archive_path, mode="r") as archive:
                file_list = archive.list()

                files_count = 0
                folders_count = 0
                total_size = 0

                for file_info in file_list:
                    if file_info.is_directory:
                        folders_count += 1
                    else:
                        files_count += 1
                        # Add file size if available
                        if (
                            hasattr(file_info, "uncompressed")
                            and file_info.uncompressed
                        ):
                            total_size += file_info.uncompressed

            return {
                "files": files_count,
                "folders": folders_count,
                "total_size": total_size,
                "format": archive_path.suffix.lower(),
            }

        except Exception as e:
            log_warning(f"Failed to get archive info: {e}")
            return {
                "files": 0,
                "folders": 0,
                "total_size": 0,
                "format": archive_path.suffix.lower(),
            }


def create_analyzer() -> ArchiveAnalyzer:
    """Create an archive analyzer instance."""
    return ArchiveAnalyzer()
