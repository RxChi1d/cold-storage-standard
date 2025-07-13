"""Archive format detection and handler selection system."""

from enum import Enum
from pathlib import Path

from coldstore.logger import log_detail


class ArchiveFormat(Enum):
    """Supported archive formats."""

    SEVEN_ZIP = "7z"
    ZIP = "zip"
    RAR = "rar"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_BZ2 = "tar.bz2"
    TAR_XZ = "tar.xz"
    GZ = "gz"
    BZ2 = "bz2"
    XZ = "xz"
    UNKNOWN = "unknown"


class FormatDetector:
    """Detects archive format based on file extension and magic bytes."""

    def __init__(self):
        # Extension-based detection mapping
        self.extension_mapping = {
            ".7z": ArchiveFormat.SEVEN_ZIP,
            ".zip": ArchiveFormat.ZIP,
            ".rar": ArchiveFormat.RAR,
            ".tar": ArchiveFormat.TAR,
            ".tar.gz": ArchiveFormat.TAR_GZ,
            ".tgz": ArchiveFormat.TAR_GZ,
            ".tar.bz2": ArchiveFormat.TAR_BZ2,
            ".tbz2": ArchiveFormat.TAR_BZ2,
            ".tar.xz": ArchiveFormat.TAR_XZ,
            ".txz": ArchiveFormat.TAR_XZ,
            ".gz": ArchiveFormat.GZ,
            ".bz2": ArchiveFormat.BZ2,
            ".xz": ArchiveFormat.XZ,
        }

        # Magic bytes for format verification
        self.magic_bytes = {
            ArchiveFormat.SEVEN_ZIP: [b"7z\xbc\xaf\x27\x1c"],
            ArchiveFormat.ZIP: [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
            ArchiveFormat.RAR: [b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"],
            ArchiveFormat.TAR: [b"ustar\x00", b"ustar\x20\x20\x00"],
            ArchiveFormat.GZ: [b"\x1f\x8b"],
            ArchiveFormat.BZ2: [b"BZ"],
            ArchiveFormat.XZ: [b"\xfd7zXZ\x00"],
        }

    def detect_format(self, file_path: Path) -> ArchiveFormat:
        """
        Detect archive format using extension and magic bytes.

        Args:
            file_path: Path to the archive file

        Returns:
            Detected archive format
        """
        if not file_path.exists() or not file_path.is_file():
            return ArchiveFormat.UNKNOWN

        # First try extension-based detection
        format_by_ext = self._detect_by_extension(file_path)

        # Then verify with magic bytes if possible
        format_by_magic = self._detect_by_magic_bytes(file_path)

        # If both methods agree, use the result
        if format_by_ext == format_by_magic:
            log_detail(
                f"Format detected by extension and magic bytes: {format_by_ext.value}"
            )
            return format_by_ext

        # If extension detection worked but magic bytes didn't, trust extension
        if format_by_ext != ArchiveFormat.UNKNOWN:
            log_detail(f"Format detected by extension: {format_by_ext.value}")
            return format_by_ext

        # If magic bytes detection worked but extension didn't, trust magic bytes
        if format_by_magic != ArchiveFormat.UNKNOWN:
            log_detail(f"Format detected by magic bytes: {format_by_magic.value}")
            return format_by_magic

        log_detail(f"Could not detect format for: {file_path}")
        return ArchiveFormat.UNKNOWN

    def _detect_by_extension(self, file_path: Path) -> ArchiveFormat:
        """Detect format based on file extension."""
        file_name = file_path.name.lower()

        # Check for compound extensions first (e.g., .tar.gz)
        for ext, fmt in sorted(
            self.extension_mapping.items(), key=lambda x: -len(x[0])
        ):
            if file_name.endswith(ext):
                return fmt

        return ArchiveFormat.UNKNOWN

    def _detect_by_magic_bytes(self, file_path: Path) -> ArchiveFormat:
        """Detect format based on magic bytes."""
        try:
            with open(file_path, "rb") as f:
                # Read first 32 bytes for magic number detection
                header = f.read(32)

                for fmt, magic_list in self.magic_bytes.items():
                    for magic in magic_list:
                        if header.startswith(magic):
                            return fmt

                # Special case for TAR - check at offset 257
                if len(header) >= 32:
                    f.seek(257)
                    tar_magic = f.read(8)
                    if tar_magic.startswith(b"ustar"):
                        return ArchiveFormat.TAR

        except OSError:
            pass

        return ArchiveFormat.UNKNOWN

    def is_supported(self, file_path: Path) -> bool:
        """Check if file format is supported."""
        format_type = self.detect_format(file_path)
        return format_type != ArchiveFormat.UNKNOWN

    def get_handler_class(self, format_type: ArchiveFormat) -> str | None:
        """Get the appropriate handler class name for the format."""
        handler_mapping = {
            ArchiveFormat.SEVEN_ZIP: "SevenZipHandler",
            ArchiveFormat.ZIP: "ZipHandler",
            ArchiveFormat.RAR: "RarHandler",
            ArchiveFormat.TAR: "TarHandler",
            ArchiveFormat.TAR_GZ: "TarHandler",
            ArchiveFormat.TAR_BZ2: "TarHandler",
            ArchiveFormat.TAR_XZ: "TarHandler",
            ArchiveFormat.GZ: "GzipHandler",
            ArchiveFormat.BZ2: "Bzip2Handler",
            ArchiveFormat.XZ: "XzHandler",
        }

        return handler_mapping.get(format_type)

    def get_format_info(self, file_path: Path) -> dict[str, str]:
        """Get comprehensive format information."""
        format_type = self.detect_format(file_path)

        return {
            "format": format_type.value,
            "extension": file_path.suffix.lower(),
            "handler": self.get_handler_class(format_type) or "Unknown",
            "supported": format_type != ArchiveFormat.UNKNOWN,
        }


def create_format_detector() -> FormatDetector:
    """Create a format detector instance."""
    return FormatDetector()
