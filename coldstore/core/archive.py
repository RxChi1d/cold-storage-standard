"""Archive handling and 7z structure detection."""

import re
import subprocess
import tempfile
from pathlib import Path

from coldstore.logging import log_detail, log_error, log_info, log_step


class ArchiveAnalyzer:
    """Intelligent 7z structure detection and handling."""

    def __init__(self):
        self.supported_formats = [".7z", ".zip", ".rar", ".tar", ".gz", ".bz2", ".xz"]
        self.temp_dir: Path | None = None

    def is_supported_archive(self, file_path: Path) -> bool:
        """Check if file is a supported archive format."""
        return any(
            str(file_path).lower().endswith(ext) for ext in self.supported_formats
        )

    def analyze_archive_structure(self, archive_path: Path) -> dict:
        """Analyze 7z archive structure to detect nested folders."""
        try:
            # Use 7z to list archive contents
            result = subprocess.run(
                ["7z", "l", "-slt", str(archive_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            entries = self._parse_7z_listing(result.stdout)
            structure_info = self._analyze_structure(entries)

            log_info(f"Archive analysis complete: {len(entries)} entries")
            log_detail(f"Structure: {structure_info['description']}")

            return structure_info

        except subprocess.CalledProcessError as e:
            log_error(f"Failed to analyze archive: {e}")
            return {
                "type": "unknown",
                "description": "Failed to analyze",
                "has_single_root": False,
                "root_folder": None,
                "entries": [],
            }

    def _parse_7z_listing(self, listing_output: str) -> list[dict]:
        """Parse 7z listing output to extract file information."""
        entries = []
        current_entry = {}

        for line in listing_output.split("\n"):
            line = line.strip()

            if line.startswith("Path = "):
                if current_entry:
                    entries.append(current_entry)
                current_entry = {
                    "path": line[7:],
                    "size": 0,
                    "is_dir": False,
                    "attributes": "",
                }
            elif line.startswith("Size = "):
                current_entry["size"] = int(line[7:]) if line[7:].isdigit() else 0
            elif line.startswith("Attributes = "):
                attrs = line[13:]
                current_entry["attributes"] = attrs
                current_entry["is_dir"] = "D" in attrs

        if current_entry:
            entries.append(current_entry)

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
        """Extract archive to specified directory."""
        try:
            log_step(f"Extracting archive: {archive_path.name}")

            # Create extraction directory
            extract_to.mkdir(parents=True, exist_ok=True)

            # Extract using 7z
            subprocess.run(
                ["7z", "x", str(archive_path), f"-o{extract_to}", "-y"],
                capture_output=True,
                text=True,
                check=True,
            )

            log_info(f"Archive extracted to: {extract_to}")
            return True

        except subprocess.CalledProcessError as e:
            log_error(f"Failed to extract archive: {e}")
            if e.stderr:
                log_detail(f"Error output: {e.stderr}")
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
        """Get comprehensive archive information."""
        try:
            result = subprocess.run(
                ["7z", "l", str(archive_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse basic info from output
            lines = result.stdout.split("\n")
            files_count = 0
            folders_count = 0
            total_size = 0

            for line in lines:
                if re.match(r"^\d{4}-\d{2}-\d{2}", line):
                    parts = line.split()
                    if len(parts) >= 5:
                        if parts[3] == "D....":
                            folders_count += 1
                        else:
                            files_count += 1
                            if parts[3].isdigit():
                                total_size += int(parts[3])

            return {
                "files": files_count,
                "folders": folders_count,
                "total_size": total_size,
                "format": archive_path.suffix.lower(),
            }

        except subprocess.CalledProcessError:
            return {
                "files": 0,
                "folders": 0,
                "total_size": 0,
                "format": archive_path.suffix.lower(),
            }


def create_analyzer() -> ArchiveAnalyzer:
    """Create an archive analyzer instance."""
    return ArchiveAnalyzer()
