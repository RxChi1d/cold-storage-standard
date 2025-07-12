"""System resource checking and validation."""

import os
import shutil
from pathlib import Path

import psutil
from rich.table import Table

from coldstore.logging import console, log_detail, log_error, log_info, log_warning


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

    def check_memory_for_decompression(self, required_memory_mb: int) -> bool:
        """Check if system has sufficient memory for decompression with specific requirements."""
        memory = psutil.virtual_memory()
        total_gb = memory.total / (1024**3)
        available_mb = memory.available / (1024**2)

        # Add some buffer (20% extra) for safety
        required_mb = int(required_memory_mb * 1.2)

        if available_mb < required_mb:
            log_warning(
                f"Low memory: {available_mb:.0f}MB available, "
                f"need {required_mb:.0f}MB for decompression"
            )
            log_info("This archive may require more memory than available")
            return False

        log_info(
            f"Memory check: {available_mb:.0f}MB/{total_gb*1024:.0f}MB available, need {required_mb:.0f}MB"
        )
        return True

    def check_disk_space_for_decompression(
        self, compressed_file: Path, output_dir: Path
    ) -> bool:
        """Check if sufficient disk space is available for decompression."""
        try:
            # Get compressed file size
            compressed_size = compressed_file.stat().st_size

            # Estimate decompressed size (compressed files usually decompress to 2-5x their size)
            # We use a conservative estimate of 5x for safety
            estimated_decompressed_size = compressed_size * 5

            # Check output directory space
            output_usage = shutil.disk_usage(output_dir.parent)
            free_space = output_usage.free

            # Add some buffer space (20% extra)
            required_space = int(estimated_decompressed_size * 1.2)

            if free_space < required_space:
                log_error(
                    f"Insufficient disk space: {free_space // (1024**3):.1f}GB available, "
                    f"estimated need {required_space // (1024**3):.1f}GB"
                )
                log_info("Note: This is a conservative estimate (5x compressed size)")
                return False

            log_info(
                f"Disk space check: {free_space // (1024**3):.1f}GB available, "
                f"estimated need {required_space // (1024**3):.1f}GB"
            )
            return True

        except OSError as e:
            log_error(f"Failed to check disk space: {e}")
            return False

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
        # All archive operations now use pure Python libraries
        # No external tools required for core functionality

        try:
            import importlib.util

            # Check if required modules are available
            required_modules = ["tarfile", "py7zr", "zstandard"]
            for module in required_modules:
                if importlib.util.find_spec(module) is None:
                    log_error(f"Required module {module} not found")
                    return False

            log_info("Tool check: All required Python libraries available")
            log_detail(
                "✅ Using py7zr for archive extraction (no system 7z dependency)"
            )
            log_detail("✅ Using Python tarfile (no system tar dependency)")
            log_detail("✅ Using python-zstandard (no system zstd dependency)")
            return True

        except ImportError as e:
            log_error(f"Missing required Python library: {e}")
            log_info(
                "Please install missing dependencies with: pip install -r requirements.txt"
            )
            return False

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

    def check_decompression_requirements(
        self,
        archive_path: Path,
        output_dir: Path,
        required_memory_mb: int,
        show_info: bool = False,
    ) -> bool:
        """Perform comprehensive system check for decompression operations."""
        if show_info:
            self.show_system_info()

        checks = [
            ("Memory", self.check_memory_for_decompression(required_memory_mb)),
            (
                "Disk Space",
                self.check_disk_space_for_decompression(archive_path, output_dir),
            ),
            ("Permissions", self.check_permissions(archive_path, output_dir)),
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
    """Convenience function for system checking (compression/packing)."""
    checker = SystemChecker()
    return checker.comprehensive_check(input_path, output_dir, long_mode, show_info)


def check_decompression_requirements(
    archive_path: Path,
    output_dir: Path,
    required_memory_mb: int,
    show_info: bool = False,
) -> bool:
    """Convenience function for decompression system checking."""
    checker = SystemChecker()
    return checker.check_decompression_requirements(
        archive_path, output_dir, required_memory_mb, show_info
    )
