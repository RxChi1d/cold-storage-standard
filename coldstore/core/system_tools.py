"""System tools availability checker for external dependencies."""

import shutil
import subprocess

from coldstore.logging import log_detail, log_error, log_info


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
