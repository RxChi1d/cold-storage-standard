"""System resource checking and validation."""

import os
import shutil
from pathlib import Path

import psutil
from rich.table import Table

from coldstore.logging import console, log_error, log_info, log_warning


class SystemChecker:
    """System resource checker matching bash script functionality."""

    def __init__(self):
        self.min_memory_gb = 2.2  # For --long=31 mode
        self.min_free_space_multiplier = 2.5  # 2.5x original file size

    def check_memory(self, long_mode: bool = True) -> bool:
        """Check if system has sufficient memory."""
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024**3)
        available_gb = memory.available / (1024**3)

        if long_mode and available_gb < self.min_memory_gb:
            log_warning(
                f"Low memory: {available_gb:.1f}GB available, "
                f"recommended {self.min_memory_gb}GB for --long mode"
            )
            log_info("Consider using --no-long to reduce memory usage")
            return False

        log_info(f"Memory check: {available_gb:.1f}GB/{total_gb:.1f}GB available")
        return True

    def check_disk_space(self, input_path: Path, output_dir: Path) -> bool:
        """Check if sufficient disk space is available."""
        try:
            # Calculate input size
            if input_path.is_file():
                input_size = input_path.stat().st_size
            else:
                input_size = sum(
                    f.stat().st_size for f in input_path.rglob("*") if f.is_file()
                )

            # Check output directory space
            output_usage = shutil.disk_usage(output_dir.parent)
            free_space = output_usage.free

            required_space = int(input_size * self.min_free_space_multiplier)

            if free_space < required_space:
                log_error(
                    f"Insufficient disk space: {free_space // (1024**3):.1f}GB available, "
                    f"need {required_space // (1024**3):.1f}GB"
                )
                return False

            log_info(
                f"Disk space check: {free_space // (1024**3):.1f}GB available, "
                f"need {required_space // (1024**3):.1f}GB"
            )
            return True

        except OSError as e:
            log_error(f"Failed to check disk space: {e}")
            return False

    def check_permissions(self, input_path: Path, output_dir: Path) -> bool:
        """Check read/write permissions."""
        # Check input path is readable
        if not os.access(input_path, os.R_OK):
            log_error(f"Cannot read input path: {input_path}")
            return False

        # Check output directory is writable
        output_dir.mkdir(parents=True, exist_ok=True)
        if not os.access(output_dir, os.W_OK):
            log_error(f"Cannot write to output directory: {output_dir}")
            return False

        log_info("Permission check: Read/write access confirmed")
        return True

    def check_required_tools(self) -> bool:
        """Check if required external tools are available."""
        required_tools = ["7z", "tar"]
        missing_tools = []

        for tool in required_tools:
            if not shutil.which(tool):
                missing_tools.append(tool)

        if missing_tools:
            log_error(f"Missing required tools: {', '.join(missing_tools)}")
            log_info("Please install missing tools before continuing")
            return False

        log_info("Tool check: All required tools available")
        return True

    def get_system_info(self) -> dict:
        """Get comprehensive system information."""
        cpu_count = psutil.cpu_count()
        memory = psutil.virtual_memory()

        return {
            "cpu_cores": cpu_count,
            "memory_total_gb": memory.total / (1024**3),
            "memory_available_gb": memory.available / (1024**3),
            "platform": psutil.os.name,
        }

    def show_system_info(self):
        """Display system information in a nice table."""
        info = self.get_system_info()

        table = Table(title="System Information")
        table.add_column("Resource", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("CPU Cores", str(info["cpu_cores"]))
        table.add_row("Total Memory", f"{info['memory_total_gb']:.1f} GB")
        table.add_row("Available Memory", f"{info['memory_available_gb']:.1f} GB")
        table.add_row("Platform", info["platform"])

        console.print(table)

    def comprehensive_check(
        self,
        input_path: Path,
        output_dir: Path,
        long_mode: bool = True,
        show_info: bool = False,
    ) -> bool:
        """Perform comprehensive system check."""
        if show_info:
            self.show_system_info()

        checks = [
            ("Memory", self.check_memory(long_mode)),
            ("Disk Space", self.check_disk_space(input_path, output_dir)),
            ("Permissions", self.check_permissions(input_path, output_dir)),
            ("Required Tools", self.check_required_tools()),
        ]

        all_passed = True
        for check_name, result in checks:
            if not result:
                all_passed = False
                log_error(f"{check_name} check failed")

        if all_passed:
            log_info("All system checks passed")
        else:
            log_error("Some system checks failed")

        return all_passed


def check_system_requirements(
    input_path: Path,
    output_dir: Path,
    long_mode: bool = True,
    show_info: bool = False,
) -> bool:
    """Convenience function for system checking."""
    checker = SystemChecker()
    return checker.comprehensive_check(input_path, output_dir, long_mode, show_info)
