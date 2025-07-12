"""Cleanup manager for temporary resources - ensures cleanup on signal interruption."""

import atexit
import platform
import signal
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from coldstore.logging import log_detail, log_info, log_warning


def _force_remove_file(file_path: Path, max_retries: int = 3) -> bool:
    """
    Force remove a file with retry logic for Windows file locking issues.

    Args:
        file_path: Path to the file to remove
        max_retries: Maximum number of retry attempts

    Returns:
        True if successfully removed, False otherwise
    """
    for attempt in range(max_retries):
        try:
            if file_path.exists():
                # Try to remove read-only attribute on Windows
                if platform.system() == "Windows":
                    try:
                        import stat

                        file_path.chmod(stat.S_IWRITE)
                    except (OSError, PermissionError):
                        pass

                file_path.unlink()
                return True
            return True  # File doesn't exist, consider it removed
        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                # Wait a bit before retrying (helps with antivirus/indexing conflicts)
                time.sleep(0.1 * (attempt + 1))
                continue
            else:
                log_warning(
                    f"Failed to remove file {file_path} after {max_retries} attempts: {e}"
                )
                return False
    return False


def _force_remove_directory(dir_path: Path, max_retries: int = 3) -> bool:
    """
    Force remove a directory with retry logic for Windows file locking issues.

    Args:
        dir_path: Path to the directory to remove
        max_retries: Maximum number of retry attempts

    Returns:
        True if successfully removed, False otherwise
    """
    import shutil

    for attempt in range(max_retries):
        try:
            if dir_path.exists():
                # On Windows, try to remove read-only attributes recursively
                if platform.system() == "Windows":
                    try:
                        import stat

                        def handle_remove_readonly(func, path, exc):
                            if exc[1].errno == 13:  # Permission denied
                                Path(path).chmod(stat.S_IWRITE)
                                func(path)
                            else:
                                raise

                        shutil.rmtree(dir_path, onerror=handle_remove_readonly)
                    except Exception:
                        # Fall back to normal removal
                        shutil.rmtree(dir_path)
                else:
                    shutil.rmtree(dir_path)
                return True
            return True  # Directory doesn't exist, consider it removed
        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                # Wait progressively longer before retrying
                time.sleep(0.2 * (attempt + 1))
                continue
            else:
                log_warning(
                    f"Failed to remove directory {dir_path} after {max_retries} attempts: {e}"
                )
                # Try to remove individual files that can be removed
                _cleanup_directory_contents(dir_path)
                return False
    return False


def _cleanup_directory_contents(dir_path: Path):
    """
    Try to clean up as many files as possible from a directory.
    This is a fallback when the entire directory can't be removed.
    """
    if not dir_path.exists():
        return

    removed_count = 0
    total_count = 0

    try:
        for item in dir_path.rglob("*"):
            total_count += 1
            if item.is_file() and _force_remove_file(item, max_retries=1):
                removed_count += 1
    except (OSError, PermissionError):
        pass

    if removed_count > 0:
        log_detail(
            f"Partially cleaned directory {dir_path}: removed {removed_count}/{total_count} items"
        )


class CleanupManager:
    """Manages cleanup of temporary resources with signal handling."""

    def __init__(self):
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._temp_directories: list[Path] = []
        self._temp_files: list[Path] = []
        self._lock = threading.Lock()
        self._signal_handlers_registered = False
        self._original_sigint_handler = None
        self._original_sigterm_handler = None

    def register_signal_handlers(self):
        """Register signal handlers for graceful cleanup."""
        if self._signal_handlers_registered:
            return

        try:
            # Store original handlers
            self._original_sigint_handler = signal.signal(
                signal.SIGINT, self._signal_handler
            )
            self._original_sigterm_handler = signal.signal(
                signal.SIGTERM, self._signal_handler
            )

            # Register atexit handler
            atexit.register(self.cleanup_all)

            self._signal_handlers_registered = True
            log_detail("Signal handlers registered for cleanup")
        except (ValueError, OSError) as e:
            log_warning(f"Failed to register signal handlers: {e}")

    def _signal_handler(self, signum: int, frame):
        """Handle signals by performing cleanup and exiting."""
        signal_name = "SIGINT" if signum == signal.SIGINT else f"SIG{signum}"
        log_info(f"Received {signal_name}, performing cleanup...")

        self.cleanup_all()

        # Restore original handler and re-raise signal
        if signum == signal.SIGINT and self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
        elif signum == signal.SIGTERM and self._original_sigterm_handler:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)

        # Exit gracefully
        import sys

        sys.exit(1)

    def add_temp_directory(self, temp_dir: Path) -> Path:
        """Register a temporary directory for cleanup."""
        with self._lock:
            if temp_dir not in self._temp_directories:
                self._temp_directories.append(temp_dir)
                log_detail(f"Registered temp directory for cleanup: {temp_dir}")
        return temp_dir

    def add_temp_file(self, temp_file: Path) -> Path:
        """Register a temporary file for cleanup."""
        with self._lock:
            if temp_file not in self._temp_files:
                self._temp_files.append(temp_file)
                log_detail(f"Registered temp file for cleanup: {temp_file}")
        return temp_file

    def add_cleanup_callback(self, callback: Callable[[], None]):
        """Register a custom cleanup callback."""
        with self._lock:
            self._cleanup_callbacks.append(callback)

    def remove_temp_directory(self, temp_dir: Path):
        """Remove a temporary directory from cleanup list (because it was already cleaned)."""
        with self._lock:
            if temp_dir in self._temp_directories:
                self._temp_directories.remove(temp_dir)

    def remove_temp_file(self, temp_file: Path):
        """Remove a temporary file from cleanup list (because it was already cleaned)."""
        with self._lock:
            if temp_file in self._temp_files:
                self._temp_files.remove(temp_file)

    def cleanup_temp_directories(self):
        """Clean up all registered temporary directories with improved error handling."""
        with self._lock:
            directories_to_clean = list(self._temp_directories)
            self._temp_directories.clear()

        success_count = 0
        failed_count = 0

        for temp_dir in directories_to_clean:
            if _force_remove_directory(temp_dir):
                log_detail(f"Cleaned up temp directory: {temp_dir}")
                success_count += 1
            else:
                failed_count += 1

        if failed_count > 0:
            log_warning(
                f"Failed to fully cleanup {failed_count} temp directories (some files may remain)"
            )

    def cleanup_temp_files(self):
        """Clean up all registered temporary files with improved error handling."""
        with self._lock:
            files_to_clean = list(self._temp_files)
            self._temp_files.clear()

        success_count = 0
        failed_count = 0

        for temp_file in files_to_clean:
            if _force_remove_file(temp_file):
                log_detail(f"Cleaned up temp file: {temp_file}")
                success_count += 1
            else:
                failed_count += 1

        if failed_count > 0:
            log_warning(f"Failed to cleanup {failed_count} temp files")

    def cleanup_callbacks(self):
        """Execute all registered cleanup callbacks."""
        with self._lock:
            callbacks_to_execute = list(self._cleanup_callbacks)
            self._cleanup_callbacks.clear()

        for callback in callbacks_to_execute:
            try:
                callback()
            except Exception as e:
                log_warning(f"Cleanup callback failed: {e}")

    def cleanup_all(self):
        """Perform complete cleanup of all resources."""
        if not self._signal_handlers_registered:
            return

        log_info("Performing cleanup of temporary resources...")

        # Execute custom callbacks first
        self.cleanup_callbacks()

        # Clean up files and directories
        self.cleanup_temp_files()
        self.cleanup_temp_directories()

        log_info("Cleanup completed")

    def cleanup_orphaned_temps(self, prefix: str = "coldstore_"):
        """Clean up any orphaned temporary files/directories from previous runs."""
        import tempfile
        import time

        temp_base = Path(tempfile.gettempdir())
        current_time = time.time()

        # Clean up directories older than 1 hour
        orphaned_dirs = []
        orphaned_files = []

        try:
            for item in temp_base.glob(f"{prefix}*"):
                # Check if older than 1 hour
                if current_time - item.stat().st_mtime > 3600:
                    if item.is_dir():
                        orphaned_dirs.append(item)
                    else:
                        orphaned_files.append(item)
        except OSError:
            pass  # Skip if we can't access temp directory

        # Clean up orphaned items with improved error handling
        cleaned_dirs = 0
        cleaned_files = 0

        for orphaned_dir in orphaned_dirs:
            if _force_remove_directory(orphaned_dir, max_retries=1):
                cleaned_dirs += 1

        for orphaned_file in orphaned_files:
            if _force_remove_file(orphaned_file, max_retries=1):
                cleaned_files += 1

        if cleaned_dirs > 0 or cleaned_files > 0:
            log_info(
                f"Cleaned up {cleaned_dirs} orphaned directories and {cleaned_files} orphaned files"
            )
            if len(orphaned_dirs) > cleaned_dirs or len(orphaned_files) > cleaned_files:
                remaining_dirs = len(orphaned_dirs) - cleaned_dirs
                remaining_files = len(orphaned_files) - cleaned_files
                log_warning(
                    f"Some orphaned items remain: {remaining_dirs} directories, {remaining_files} files"
                )


# Global cleanup manager instance
_cleanup_manager = CleanupManager()


def get_cleanup_manager() -> CleanupManager:
    """Get the global cleanup manager instance."""
    return _cleanup_manager


def initialize_cleanup():
    """Initialize the cleanup system with signal handlers."""
    _cleanup_manager.register_signal_handlers()
    _cleanup_manager.cleanup_orphaned_temps()


def create_managed_temp_dir(prefix: str = "coldstore_") -> Path:
    """Create a temporary directory that will be automatically cleaned up."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    _cleanup_manager.add_temp_directory(temp_dir)
    return temp_dir


def create_managed_temp_file(prefix: str = "coldstore_", suffix: str = "") -> Path:
    """Create a temporary file that will be automatically cleaned up."""
    fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    import os

    os.close(fd)  # Close the file descriptor, we just want the path
    temp_file = Path(temp_path)
    _cleanup_manager.add_temp_file(temp_file)
    return temp_file


def register_cleanup_callback(callback: Callable[[], None]):
    """Register a custom cleanup callback."""
    _cleanup_manager.add_cleanup_callback(callback)


def manual_cleanup():
    """Manually trigger cleanup of all resources."""
    _cleanup_manager.cleanup_all()
