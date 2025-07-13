"""Archive handlers for different formats with unified interface."""

import bz2
import gzip
import lzma
import platform
import re
import tarfile
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

import py7zr

from coldstore.logger import log_detail, log_error, log_info, log_warning


def sanitize_filename_for_windows(filename: str) -> str:
    """
    Clean filename to be valid on Windows systems.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for Windows
    """
    if not filename:
        return filename

    # Replace Windows invalid characters with underscores
    invalid_chars = '<>:"|?*'
    sanitized = filename
    for char in invalid_chars:
        sanitized = sanitized.replace(char, "_")

    # Replace control characters (0-31) and DEL (127)
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "_", sanitized)

    # Remove trailing dots and spaces (Windows doesn't allow these)
    sanitized = sanitized.rstrip(". ")

    # Handle Windows reserved names
    reserved_names = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }

    # Check if the filename (without extension) is a reserved name
    name_part = Path(sanitized).stem.upper()
    if name_part in reserved_names:
        extension = Path(sanitized).suffix
        sanitized = f"{name_part}_file{extension}"

    # Limit filename length (Windows has a 255 character limit for filenames)
    if len(sanitized) > 255:
        name_part = Path(sanitized).stem
        extension = Path(sanitized).suffix
        max_name_length = 255 - len(extension)
        if max_name_length > 0:
            sanitized = name_part[:max_name_length] + extension
        else:
            sanitized = sanitized[:255]

    # Ensure we don't return an empty filename
    if not sanitized or sanitized in (".", ".."):
        sanitized = "renamed_file"

    return sanitized


def sanitize_path_for_windows(path: str) -> str:
    """
    Clean entire path to be valid on Windows systems.

    Args:
        path: Original path string

    Returns:
        Sanitized path safe for Windows
    """
    if not path:
        return path

    # Split path into components and sanitize each part
    path_obj = Path(path)
    parts = list(path_obj.parts)

    sanitized_parts = []
    for part in parts:
        if part in ("/", "\\"):  # Skip root separators
            continue
        sanitized_part = sanitize_filename_for_windows(part)
        sanitized_parts.append(sanitized_part)

    # Reconstruct the path
    if not sanitized_parts:
        return "extracted_file"

    return str(Path(*sanitized_parts))


def needs_windows_sanitization() -> bool:
    """Check if we need to apply Windows filename sanitization."""
    return platform.system() == "Windows"


class ArchiveEntry:
    """Unified representation of archive entries."""

    def __init__(
        self, path: str, size: int, is_dir: bool, compressed_size: int | None = None
    ):
        self.path = path
        self.size = size
        self.is_dir = is_dir
        self.compressed_size = compressed_size


class BaseArchiveHandler(ABC):
    """Base class for all archive handlers."""

    def __init__(self, archive_path: Path):
        self.archive_path = archive_path
        self.format_name = "unknown"

    @abstractmethod
    def list_contents(self) -> list[ArchiveEntry]:
        """List all entries in the archive."""
        pass

    @abstractmethod
    def extract_all(self, extract_to: Path) -> bool:
        """Extract all contents to the specified directory."""
        pass

    @abstractmethod
    def get_archive_info(self) -> dict[str, any]:
        """Get archive metadata information."""
        pass

    def is_supported(self) -> bool:
        """Check if this handler can process the archive."""
        return self.archive_path.exists() and self.archive_path.is_file()


class SevenZipHandler(BaseArchiveHandler):
    """Handler for 7z format archives."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "7z"

    def list_contents(self) -> list[ArchiveEntry]:
        """List all entries in the 7z archive."""
        entries = []
        try:
            with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
                file_list = archive.list()
                for file_info in file_list:
                    entry = ArchiveEntry(
                        path=file_info.filename,
                        size=file_info.uncompressed
                        if hasattr(file_info, "uncompressed")
                        else 0,
                        is_dir=file_info.is_directory,
                        compressed_size=file_info.compressed
                        if hasattr(file_info, "compressed")
                        else None,
                    )
                    entries.append(entry)
        except Exception as e:
            log_error(f"Failed to list 7z contents: {e}")

        return entries

    def extract_all(self, extract_to: Path) -> bool:
        """Extract all contents from 7z archive."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)

            with py7zr.SevenZipFile(self.archive_path, mode="r") as archive:
                if needs_windows_sanitization():
                    # Manual extraction with filename sanitization
                    renamed_files = []

                    # Get all files with their data
                    all_files = archive.readall()

                    for original_path, file_data in all_files.items():
                        sanitized_path = sanitize_path_for_windows(original_path)

                        if original_path != sanitized_path:
                            renamed_files.append((original_path, sanitized_path))

                        # Create target path
                        target_path = extract_to / sanitized_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Write file data if it's not a directory
                        if file_data and not original_path.endswith("/"):
                            with open(target_path, "wb") as f:
                                f.write(file_data.read())

                    # Log renamed files
                    if renamed_files:
                        log_info(
                            f"Renamed {len(renamed_files)} files for Windows compatibility:"
                        )
                        for original, sanitized in renamed_files:
                            log_detail(f"  '{original}' -> '{sanitized}'")
                else:
                    # Standard extraction for non-Windows platforms
                    archive.extractall(path=extract_to)

            log_info(f"7z archive extracted to: {extract_to}")
            return True
        except Exception as e:
            log_error(f"Failed to extract 7z archive: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get 7z archive information."""
        info = {
            "format": self.format_name,
            "files": 0,
            "folders": 0,
            "total_size": 0,
            "compressed_size": self.archive_path.stat().st_size,
        }

        try:
            entries = self.list_contents()
            for entry in entries:
                if entry.is_dir:
                    info["folders"] += 1
                else:
                    info["files"] += 1
                    info["total_size"] += entry.size
        except Exception as e:
            log_warning(f"Failed to get 7z info: {e}")

        return info


class ZipHandler(BaseArchiveHandler):
    """Handler for ZIP format archives."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "zip"

    def list_contents(self) -> list[ArchiveEntry]:
        """List all entries in the ZIP archive."""
        entries = []
        try:
            with zipfile.ZipFile(self.archive_path, "r") as archive:
                for info in archive.infolist():
                    entry = ArchiveEntry(
                        path=info.filename,
                        size=info.file_size,
                        is_dir=info.is_dir(),
                        compressed_size=info.compress_size,
                    )
                    entries.append(entry)
        except Exception as e:
            log_error(f"Failed to list ZIP contents: {e}")

        return entries

    def extract_all(self, extract_to: Path) -> bool:
        """Extract all contents from ZIP archive."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(self.archive_path, "r") as archive:
                if needs_windows_sanitization():
                    # Manual extraction with filename sanitization
                    renamed_files = []

                    for info in archive.infolist():
                        original_path = info.filename
                        sanitized_path = sanitize_path_for_windows(original_path)

                        if original_path != sanitized_path:
                            renamed_files.append((original_path, sanitized_path))

                        # Create target path
                        target_path = extract_to / sanitized_path

                        # Skip directories or create them
                        if original_path.endswith("/") or info.is_dir():
                            target_path.mkdir(parents=True, exist_ok=True)
                            continue

                        # Ensure parent directory exists
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Extract file content
                        with archive.open(info) as source, open(
                            target_path, "wb"
                        ) as target:
                            target.write(source.read())

                    # Log renamed files
                    if renamed_files:
                        log_info(
                            f"Renamed {len(renamed_files)} files for Windows compatibility:"
                        )
                        for original, sanitized in renamed_files:
                            log_detail(f"  '{original}' -> '{sanitized}'")
                else:
                    # Standard extraction for non-Windows platforms
                    archive.extractall(path=extract_to)

            log_info(f"ZIP archive extracted to: {extract_to}")
            return True
        except Exception as e:
            log_error(f"Failed to extract ZIP archive: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get ZIP archive information."""
        info = {
            "format": self.format_name,
            "files": 0,
            "folders": 0,
            "total_size": 0,
            "compressed_size": self.archive_path.stat().st_size,
        }

        try:
            entries = self.list_contents()
            for entry in entries:
                if entry.is_dir:
                    info["folders"] += 1
                else:
                    info["files"] += 1
                    info["total_size"] += entry.size
        except Exception as e:
            log_warning(f"Failed to get ZIP info: {e}")

        return info


class RarHandler(BaseArchiveHandler):
    """Handler for RAR format archives with proper system tool validation."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "rar"
        self.unrar_available = False
        self._validate_rar_support()

    def _validate_rar_support(self) -> bool:
        """Validate RAR processing capabilities upfront."""
        from coldstore.core.system_tools import create_system_tool_checker

        # Check system tools first
        tool_checker = create_system_tool_checker()
        unrar_available, version_info = tool_checker.check_unrar_availability()

        if not unrar_available:
            log_error("RAR processing not available: unrar tool not found")
            log_info("Required: unrar tool must be installed")
            for rec in tool_checker.get_rar_processing_requirements()[
                "recommendations"
            ]:
                log_info(f"  • {rec}")
            self.unrar_available = False
            return False

        # Check if rarfile library can use the system tools
        try:
            import rarfile

            # Test basic file opening (this will fail fast if tools aren't working)
            with rarfile.RarFile(self.archive_path, "r") as archive:
                # Just try to get basic info without extracting
                archive.infolist()

            log_info(f"RAR processing ready: {version_info}")
            self.unrar_available = True
            return True

        except rarfile.RarCannotExec as e:
            log_error(f"RAR processing failed: cannot execute unrar tool - {e}")
            self.unrar_available = False
            return False
        except rarfile.BadRarFile as e:
            log_error(f"Invalid RAR file: {e}")
            self.unrar_available = False
            return False
        except Exception as e:
            log_error(f"RAR processing error: {e}")
            self.unrar_available = False
            return False

    def list_contents(self) -> list[ArchiveEntry]:
        """List all entries in the RAR archive."""
        entries = []

        # Check if unrar is available
        if not self.unrar_available:
            log_error("Cannot list RAR contents: unrar tool not available")
            return entries

        # Process with rarfile
        try:
            import rarfile

            with rarfile.RarFile(self.archive_path, "r") as archive:
                for info in archive.infolist():
                    entry = ArchiveEntry(
                        path=info.filename,
                        size=info.file_size,
                        is_dir=info.is_dir(),
                        compressed_size=info.compress_size,
                    )
                    entries.append(entry)
            return entries
        except Exception as e:
            log_error(f"Failed to list RAR contents: {e}")
            log_detail("This error occurred even though unrar tool is available")
            log_detail("The issue may be with the RAR file itself or rarfile library")
            return entries

    def extract_all(self, extract_to: Path) -> bool:
        """Extract all contents from RAR archive."""
        extract_to.mkdir(parents=True, exist_ok=True)

        # Check if unrar is available
        if not self.unrar_available:
            log_error("Cannot extract RAR archive: unrar tool not available")
            return False

        # Process with rarfile
        try:
            import rarfile

            with rarfile.RarFile(self.archive_path, "r") as archive:
                archive.extractall(path=extract_to)
            log_info(f"RAR archive extracted to: {extract_to}")
            return True
        except Exception as e:
            log_error(f"Failed to extract RAR archive: {e}")
            log_detail("This error occurred even though unrar tool is available")
            log_detail("The issue may be with the RAR file itself or rarfile library")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get RAR archive information."""
        info = {
            "format": self.format_name,
            "files": 0,
            "folders": 0,
            "total_size": 0,
            "compressed_size": self.archive_path.stat().st_size,
        }

        try:
            entries = self.list_contents()
            for entry in entries:
                if entry.is_dir:
                    info["folders"] += 1
                else:
                    info["files"] += 1
                    info["total_size"] += entry.size
        except Exception as e:
            log_warning(f"Failed to get RAR info: {e}")

        return info


class TarHandler(BaseArchiveHandler):
    """Handler for TAR format archives (including tar.gz, tar.bz2, tar.xz)."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = self._detect_tar_format(archive_path)

    def _detect_tar_format(self, archive_path: Path) -> str:
        """Detect specific TAR format."""
        name = archive_path.name.lower()
        if name.endswith(".tar.gz") or name.endswith(".tgz"):
            return "tar.gz"
        elif name.endswith(".tar.bz2") or name.endswith(".tbz2"):
            return "tar.bz2"
        elif name.endswith(".tar.xz") or name.endswith(".txz"):
            return "tar.xz"
        else:
            return "tar"

    def list_contents(self) -> list[ArchiveEntry]:
        """List all entries in the TAR archive."""
        entries = []
        try:
            with tarfile.open(self.archive_path, "r:*") as archive:
                for member in archive.getmembers():
                    entry = ArchiveEntry(
                        path=member.name,
                        size=member.size if member.size else 0,
                        is_dir=member.isdir(),
                    )
                    entries.append(entry)
        except Exception as e:
            log_error(f"Failed to list TAR contents: {e}")

        return entries

    def extract_all(self, extract_to: Path) -> bool:
        """Extract all contents from TAR archive."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)

            with tarfile.open(self.archive_path, "r:*") as archive:
                if needs_windows_sanitization():
                    # Manual extraction with filename sanitization
                    renamed_files = []

                    for member in archive.getmembers():
                        original_path = member.name
                        sanitized_path = sanitize_path_for_windows(original_path)

                        if original_path != sanitized_path:
                            renamed_files.append((original_path, sanitized_path))

                        # Create target path
                        target_path = extract_to / sanitized_path

                        # Handle directories
                        if member.isdir():
                            target_path.mkdir(parents=True, exist_ok=True)
                            continue

                        # Ensure parent directory exists
                        target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Extract file
                        if member.isfile():
                            with archive.extractfile(member) as source:
                                if source:
                                    with open(target_path, "wb") as target:
                                        target.write(source.read())
                        elif member.islnk() or member.issym():
                            # Handle links by copying the original member extraction
                            # but to the sanitized path
                            original_member = member
                            member.name = sanitized_path
                            archive.extract(member, path=extract_to)
                            member.name = original_member.name  # Restore original name

                    # Log renamed files
                    if renamed_files:
                        log_info(
                            f"Renamed {len(renamed_files)} files for Windows compatibility:"
                        )
                        for original, sanitized in renamed_files:
                            log_detail(f"  '{original}' -> '{sanitized}'")
                else:
                    # Standard extraction for non-Windows platforms
                    archive.extractall(path=extract_to)

            log_info(f"TAR archive extracted to: {extract_to}")
            return True
        except Exception as e:
            log_error(f"Failed to extract TAR archive: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get TAR archive information."""
        info = {
            "format": self.format_name,
            "files": 0,
            "folders": 0,
            "total_size": 0,
            "compressed_size": self.archive_path.stat().st_size,
        }

        try:
            entries = self.list_contents()
            for entry in entries:
                if entry.is_dir:
                    info["folders"] += 1
                else:
                    info["files"] += 1
                    info["total_size"] += entry.size
        except Exception as e:
            log_warning(f"Failed to get TAR info: {e}")

        return info


class GzipHandler(BaseArchiveHandler):
    """Handler for standalone GZIP files."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "gzip"

    def list_contents(self) -> list[ArchiveEntry]:
        """List contents of GZIP file (single file)."""
        # GZIP typically contains a single file
        stem = self.archive_path.stem
        try:
            with gzip.open(self.archive_path, "rb") as f:
                # Try to determine uncompressed size
                f.seek(0, 2)  # Seek to end
                size = f.tell()

            entry = ArchiveEntry(
                path=stem,
                size=size,
                is_dir=False,
                compressed_size=self.archive_path.stat().st_size,
            )
            return [entry]
        except Exception as e:
            log_error(f"Failed to analyze GZIP file: {e}")
            return []

    def extract_all(self, extract_to: Path) -> bool:
        """Extract GZIP file."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            output_file = extract_to / self.archive_path.stem

            with (
                gzip.open(self.archive_path, "rb") as f_in,
                open(output_file, "wb") as f_out,
            ):
                f_out.write(f_in.read())

            log_info(f"GZIP file extracted to: {output_file}")
            return True
        except Exception as e:
            log_error(f"Failed to extract GZIP file: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get GZIP file information."""
        entries = self.list_contents()
        return {
            "format": self.format_name,
            "files": len(entries),
            "folders": 0,
            "total_size": entries[0].size if entries else 0,
            "compressed_size": self.archive_path.stat().st_size,
        }


class Bzip2Handler(BaseArchiveHandler):
    """Handler for standalone BZIP2 files."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "bzip2"

    def list_contents(self) -> list[ArchiveEntry]:
        """List contents of BZIP2 file (single file)."""
        stem = self.archive_path.stem
        try:
            with bz2.open(self.archive_path, "rb") as f:
                # Read to determine uncompressed size
                data = f.read()
                size = len(data)

            entry = ArchiveEntry(
                path=stem,
                size=size,
                is_dir=False,
                compressed_size=self.archive_path.stat().st_size,
            )
            return [entry]
        except Exception as e:
            log_error(f"Failed to analyze BZIP2 file: {e}")
            return []

    def extract_all(self, extract_to: Path) -> bool:
        """Extract BZIP2 file."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            output_file = extract_to / self.archive_path.stem

            with (
                bz2.open(self.archive_path, "rb") as f_in,
                open(output_file, "wb") as f_out,
            ):
                f_out.write(f_in.read())

            log_info(f"BZIP2 file extracted to: {output_file}")
            return True
        except Exception as e:
            log_error(f"Failed to extract BZIP2 file: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get BZIP2 file information."""
        entries = self.list_contents()
        return {
            "format": self.format_name,
            "files": len(entries),
            "folders": 0,
            "total_size": entries[0].size if entries else 0,
            "compressed_size": self.archive_path.stat().st_size,
        }


class XzHandler(BaseArchiveHandler):
    """Handler for standalone XZ files."""

    def __init__(self, archive_path: Path):
        super().__init__(archive_path)
        self.format_name = "xz"

    def list_contents(self) -> list[ArchiveEntry]:
        """List contents of XZ file (single file)."""
        stem = self.archive_path.stem
        try:
            with lzma.open(self.archive_path, "rb") as f:
                # Read to determine uncompressed size
                data = f.read()
                size = len(data)

            entry = ArchiveEntry(
                path=stem,
                size=size,
                is_dir=False,
                compressed_size=self.archive_path.stat().st_size,
            )
            return [entry]
        except Exception as e:
            log_error(f"Failed to analyze XZ file: {e}")
            return []

    def extract_all(self, extract_to: Path) -> bool:
        """Extract XZ file."""
        try:
            extract_to.mkdir(parents=True, exist_ok=True)
            output_file = extract_to / self.archive_path.stem

            with (
                lzma.open(self.archive_path, "rb") as f_in,
                open(output_file, "wb") as f_out,
            ):
                f_out.write(f_in.read())

            log_info(f"XZ file extracted to: {output_file}")
            return True
        except Exception as e:
            log_error(f"Failed to extract XZ file: {e}")
            return False

    def get_archive_info(self) -> dict[str, any]:
        """Get XZ file information."""
        entries = self.list_contents()
        return {
            "format": self.format_name,
            "files": len(entries),
            "folders": 0,
            "total_size": entries[0].size if entries else 0,
            "compressed_size": self.archive_path.stat().st_size,
        }


def create_handler(archive_path: Path, format_name: str) -> BaseArchiveHandler | None:
    """Create appropriate handler based on format name."""
    handler_mapping = {
        "7z": SevenZipHandler,
        "zip": ZipHandler,
        "rar": RarHandler,
        "tar": TarHandler,
        "tar.gz": TarHandler,
        "tar.bz2": TarHandler,
        "tar.xz": TarHandler,
        "gz": GzipHandler,
        "bz2": Bzip2Handler,
        "xz": XzHandler,
    }

    handler_class = handler_mapping.get(format_name.lower())
    if handler_class:
        return handler_class(archive_path)

    log_error(f"No handler available for format: {format_name}")
    return None
