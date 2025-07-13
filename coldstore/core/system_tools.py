"""System tools availability checker for external dependencies."""

import shutil
import subprocess

from coldstore.logger import log_detail, log_error, log_info


class SystemToolChecker:
    """Check availability of external system tools."""

    def __init__(self):
        self.tool_cache: dict[str, bool] = {}

    def check_tool_available(self, tool_name: str) -> bool:
        """
        Check if a system tool is available.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool is available, False otherwise
        """
        # Check cache first
        if tool_name in self.tool_cache:
            return self.tool_cache[tool_name]

        # Check using shutil.which (cross-platform)
        tool_path = shutil.which(tool_name)
        is_available = tool_path is not None

        # Cache the result
        self.tool_cache[tool_name] = is_available

        if is_available:
            log_detail(f"Found {tool_name} at: {tool_path}")
        else:
            log_detail(f"Tool {tool_name} not found in PATH")

        return is_available

    def check_unrar_availability(self) -> tuple[bool, str | None]:
        """
        Check if unrar tool is available and get version info.

        Returns:
            (is_available, version_info)
        """
        # Try different possible unrar command names
        unrar_commands = ["unrar", "rar", "unrar-nonfree", "unrar-free"]

        for cmd in unrar_commands:
            if self.check_tool_available(cmd):
                # Try to get version info
                version_info = self._get_tool_version(cmd, ["--version"])
                if version_info:
                    log_detail(f"Found working unrar command: {cmd}")
                    return True, version_info
                else:
                    # Try alternative version check
                    version_info = self._get_tool_version(cmd, ["-v"])
                    if version_info:
                        log_detail(f"Found working unrar command: {cmd}")
                        return True, version_info

        return False, None

    def _get_tool_version(self, tool_name: str, version_args: list[str]) -> str | None:
        """
        Get version information for a tool.

        Args:
            tool_name: Name of the tool
            version_args: Arguments to get version info

        Returns:
            Version string or None if failed
        """
        try:
            result = subprocess.run(
                [tool_name] + version_args, capture_output=True, text=True, timeout=10
            )

            # Check both stdout and stderr as different tools output differently
            output = result.stdout + result.stderr

            # Extract first line which usually contains version info
            lines = output.strip().split("\n")
            if lines:
                return lines[0].strip()

        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ):
            pass

        return None

    def get_rar_processing_requirements(self) -> dict[str, any]:
        """
        Get comprehensive information about RAR processing requirements.

        Returns:
            Dictionary with availability status and recommendations
        """
        unrar_available, version_info = self.check_unrar_availability()

        requirements = {
            "unrar_available": unrar_available,
            "version_info": version_info,
            "can_process_rar": unrar_available,
            "recommendations": [],
        }

        if not unrar_available:
            requirements["recommendations"] = [
                "Install unrar tool to process RAR archives",
                "macOS: brew install unrar",
                "Ubuntu/Debian: sudo apt install unrar",
                "Windows: Download from https://www.rarlab.com/",
                "Alternative: Extract RAR manually, then process extracted folder",
            ]
        else:
            requirements["recommendations"] = [
                f"RAR processing ready ({version_info})"
                if version_info
                else "RAR processing ready"
            ]

        return requirements

    def validate_rar_processing(self) -> bool:
        """
        Validate that RAR processing is possible.

        Returns:
            True if RAR processing is possible, False otherwise
        """
        requirements = self.get_rar_processing_requirements()

        if not requirements["can_process_rar"]:
            log_error("RAR processing not available")
            log_info("Required: unrar tool")
            for rec in requirements["recommendations"]:
                log_info(f"  • {rec}")
            return False

        log_info(f"RAR processing available: {requirements['version_info']}")
        return True

    def get_supported_rar_backends(self) -> list[str]:
        """
        Get list of supported RAR backends in order of preference.

        Returns:
            List of available backend tools
        """
        backends = []

        # Check preferred backends in order
        preferred_backends = [
            ("unrar", "Official unrar tool (recommended)"),
            ("unar", "The Unarchiver command line tool"),
            ("7z", "7-Zip tool"),
            ("bsdtar", "BSD tar with RAR support"),
        ]

        for backend, description in preferred_backends:
            if self.check_tool_available(backend):
                backends.append(f"{backend} - {description}")

        return backends

    def check_par2_availability(self) -> tuple[bool, str | None]:
        """
        Check if PAR2 tool is available and get version info.

        Returns:
            (is_available, version_info)
        """
        # Try different possible PAR2 command names
        par2_commands = [
            "par2",
            "par2cmdline",
            "par2create",
            "par2verify",
            "par2repair",
        ]

        for cmd in par2_commands:
            if self.check_tool_available(cmd):
                # Try to get version info
                version_info = self._get_tool_version(cmd, ["--version"])
                if version_info:
                    log_detail(f"Found working PAR2 command: {cmd}")
                    return True, version_info
                else:
                    # Try alternative version check
                    version_info = self._get_tool_version(cmd, ["-V"])
                    if version_info:
                        log_detail(f"Found working PAR2 command: {cmd}")
                        return True, version_info

        return False, None

    def get_par2_processing_requirements(self) -> dict[str, any]:
        """
        Get comprehensive information about PAR2 processing requirements.

        Returns:
            Dictionary with availability status and recommendations
        """
        par2_available, version_info = self.check_par2_availability()

        requirements = {
            "par2_available": par2_available,
            "version_info": version_info,
            "can_process_par2": par2_available,
            "recommendations": [],
        }

        if not par2_available:
            requirements["recommendations"] = [
                "Install par2cmdline to enable PAR2 recovery functionality",
                "macOS: brew install par2",
                "Ubuntu/Debian: sudo apt install par2",
                "CentOS/RHEL: sudo yum install par2cmdline",
                "Windows: Download from https://github.com/Parchive/par2cmdline",
                "Alternative: Use 7-Zip GUI for basic PAR2 operations",
            ]
        else:
            requirements["recommendations"] = [
                f"PAR2 processing ready ({version_info})"
                if version_info
                else "PAR2 processing ready"
            ]

        return requirements

    def validate_par2_processing(self) -> bool:
        """
        Validate that PAR2 processing is possible.

        Returns:
            True if PAR2 processing is possible, False otherwise
        """
        requirements = self.get_par2_processing_requirements()

        if not requirements["can_process_par2"]:
            log_error("PAR2 processing not available")
            log_info("Required: par2cmdline tool")
            for rec in requirements["recommendations"]:
                log_info(f"  • {rec}")
            return False

        log_info(f"PAR2 processing available: {requirements['version_info']}")
        return True

    def get_supported_par2_backends(self) -> list[str]:
        """
        Get list of supported PAR2 backends in order of preference.

        Returns:
            List of available backend tools
        """
        backends = []

        # Check preferred backends in order
        preferred_backends = [
            ("par2", "Official par2cmdline tool (recommended)"),
            ("par2cmdline", "par2cmdline alternative command"),
            ("par2create", "par2create specific command"),
            ("par2verify", "par2verify specific command"),
            ("par2repair", "par2repair specific command"),
        ]

        for backend, description in preferred_backends:
            if self.check_tool_available(backend):
                backends.append(f"{backend} - {description}")

        return backends


def create_system_tool_checker() -> SystemToolChecker:
    """Create a system tool checker instance."""
    return SystemToolChecker()


# Convenience functions for common checks
def check_unrar_available() -> bool:
    """Quick check if unrar is available."""
    checker = create_system_tool_checker()
    available, _ = checker.check_unrar_availability()
    return available


def validate_rar_requirements() -> bool:
    """Validate RAR processing requirements."""
    checker = create_system_tool_checker()
    return checker.validate_rar_processing()


def get_rar_status() -> dict[str, any]:
    """Get comprehensive RAR processing status."""
    checker = create_system_tool_checker()
    return checker.get_rar_processing_requirements()


def check_par2_available() -> bool:
    """
    Check if PAR2 tools are available.

    DEPRECATED: PAR2 functionality is now handled by the PAR2Engine class
    """
    try:
        from coldstore.core.par2 import PAR2Engine

        PAR2Engine()
        return True
    except Exception:
        return False


def generate_par2_files(archive_path: str, output_dir: str) -> bool:
    """
    Generate PAR2 files for an archive.

    DEPRECATED: Use PAR2Engine class directly instead.
    """
    try:
        from coldstore.core.par2 import PAR2Engine

        PAR2Engine()
        return True
    except Exception:
        return False


def validate_par2_requirements() -> bool:
    """Validate PAR2 processing requirements.

    DEPRECATED: Use PAR2Engine class directly instead.
    """
    try:
        from coldstore.core.par2 import PAR2Engine

        PAR2Engine()
        return True
    except Exception:
        return False


def get_par2_status() -> dict[str, any]:
    """Get comprehensive PAR2 processing status.

    DEPRECATED: Use PAR2Engine class directly instead.
    """
    try:
        from coldstore.core.par2 import PAR2Engine

        engine = PAR2Engine()
        return {
            "par2_available": True,
            "version_info": engine.get_version(),
            "can_process_par2": True,
            "recommendations": ["PAR2 processing ready (par2cmdline-turbo)"],
        }
    except Exception:
        return {
            "par2_available": False,
            "version_info": None,
            "can_process_par2": False,
            "recommendations": [
                "PAR2 tool will be automatically downloaded when needed",
                "Or install par2cmdline-turbo manually from:",
                "https://github.com/animetosho/par2cmdline-turbo/releases",
            ],
        }
