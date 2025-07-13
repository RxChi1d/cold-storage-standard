"""PAR2 recovery file system for Cold Storage Standard."""

import os
import shutil
import subprocess
from typing import Any

from ..logger import log_error, log_info, log_warning


def logger_info(msg):
    log_info(msg, prefix="[PAR2]")


def logger_warning(msg):
    log_warning(msg, prefix="[PAR2]")


def logger_error(msg):
    log_error(msg, prefix="[PAR2]")


class Logger:
    def info(self, msg):
        logger_info(msg)

    def warning(self, msg):
        logger_warning(msg)

    def error(self, msg):
        logger_error(msg)


logger = Logger()


class PAR2Error(Exception):
    """Base exception for PAR2 operations"""

    pass


class PAR2ToolNotFoundError(PAR2Error):
    """Raised when PAR2 tool is not available"""

    pass


class PAR2GenerationError(PAR2Error):
    """Raised when PAR2 generation fails"""

    pass


class PAR2VerificationError(PAR2Error):
    """Raised when PAR2 verification fails"""

    pass


class PAR2RepairError(PAR2Error):
    """Raised when PAR2 repair fails"""

    pass


class PAR2Engine:
    """High-performance PAR2 engine using par2cmdline-turbo"""

    def __init__(self, recovery_percent: int = 10):
        """
        Initialize PAR2Engine

        Args:
            recovery_percent: Recovery data percentage (default: 10%)
        """
        self.recovery_percent = recovery_percent
        self.par2_path = self._find_par2_command()

    def _find_par2_command(self) -> str:
        """Find par2 command in system PATH"""
        par2_path = shutil.which("par2")

        if not par2_path:
            raise PAR2ToolNotFoundError(
                "par2 command not found in PATH. "
                "Please ensure par2cmdline-turbo is installed via 'uv add par2cmdline-turbo'"
            )

        # Verify it's par2cmdline-turbo
        try:
            result = subprocess.run(
                [par2_path, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "turbo" in result.stdout.lower():
                logger.info(f"Found par2cmdline-turbo at: {par2_path}")
                return par2_path
            else:
                logger.warning(
                    f"Found par2 at {par2_path} but it may not be par2cmdline-turbo"
                )
                return par2_path
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            logger.warning(f"Found par2 at {par2_path} but could not verify version")
            return par2_path

    def _run_par2_command(
        self, args: list[str], cwd: str | None = None
    ) -> subprocess.CompletedProcess:
        """Run par2 command with error handling"""
        cmd = [self.par2_path] + args

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )
            return result
        except subprocess.TimeoutExpired:
            raise PAR2Error("PAR2 operation timed out") from None
        except subprocess.SubprocessError as e:
            raise PAR2Error(f"Failed to run par2 command: {e}") from e

    def generate_par2(
        self, archive_path: str, output_dir: str | None = None
    ) -> list[str]:
        """
        Generate PAR2 files for an archive

        Args:
            archive_path: Path to the archive file
            output_dir: Directory to store PAR2 files (default: same as archive)

        Returns:
            List of generated PAR2 file paths
        """
        if not os.path.exists(archive_path):
            raise PAR2GenerationError(f"Archive file not found: {archive_path}")

        if output_dir is None:
            output_dir = os.path.dirname(archive_path)

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate PAR2 base name
        archive_name = os.path.basename(archive_path)
        par2_base = os.path.join(output_dir, f"{archive_name}.par2")

        # PAR2 creation command
        args = [
            "create",
            f"-r{self.recovery_percent}",  # Recovery percentage (configurable)
            "-s1048576",  # 1MB slice size (1024*1024 bytes)
            "-n1",  # 1 recovery file
            par2_base,
            archive_path,
        ]

        logger.info(
            f"Generating PAR2 files for {archive_path} with {self.recovery_percent}% recovery, 1MB slice size"
        )

        result = self._run_par2_command(args)

        if result.returncode != 0:
            error_msg = f"PAR2 generation failed: {result.stderr}"
            logger.error(error_msg)
            raise PAR2GenerationError(error_msg)

        # Find generated PAR2 files
        par2_files = []
        for file in os.listdir(output_dir):
            if file.startswith(archive_name) and file.endswith(".par2"):
                par2_files.append(os.path.join(output_dir, file))

        logger.info(f"Generated {len(par2_files)} PAR2 files")
        return sorted(par2_files)

    def verify_par2(self, par2_file: str) -> dict[str, Any]:
        """
        Verify files using PAR2

        Args:
            par2_file: Path to the main PAR2 file

        Returns:
            Dictionary with verification results
        """
        if not os.path.exists(par2_file):
            raise PAR2VerificationError(f"PAR2 file not found: {par2_file}")

        args = ["verify", par2_file]

        logger.info(f"Verifying files using {par2_file}")

        result = self._run_par2_command(args)

        # Parse verification results
        success = result.returncode == 0
        output = result.stdout
        error = result.stderr

        # Parse details from output
        files_verified = output.count("Target:") if output else 0
        files_missing = output.count("missing") if output else 0
        files_damaged = output.count("damaged") if output else 0
        repairable = "repair is required" in output if output else False

        return {
            "success": success,
            "files_verified": files_verified,
            "files_missing": files_missing,
            "files_damaged": files_damaged,
            "repairable": repairable,
            "output": output,
            "error": error,
        }

    def repair_files(self, par2_file: str) -> dict[str, Any]:
        """
        Repair files using PAR2

        Args:
            par2_file: Path to the main PAR2 file

        Returns:
            Dictionary with repair results
        """
        if not os.path.exists(par2_file):
            raise PAR2RepairError(f"PAR2 file not found: {par2_file}")

        args = ["repair", par2_file]

        logger.info(f"Repairing files using {par2_file}")

        result = self._run_par2_command(args)

        # Parse repair results
        success = result.returncode == 0
        output = result.stdout
        error = result.stderr

        files_repaired = output.count("repaired") if output else 0
        files_created = output.count("created") if output else 0

        return {
            "success": success,
            "files_repaired": files_repaired,
            "files_created": files_created,
            "output": output,
            "error": error,
        }

    def get_version(self) -> str:
        """Get PAR2 tool version"""
        result = self._run_par2_command(["--version"])
        return result.stdout.strip() if result.stdout else "Unknown version"
