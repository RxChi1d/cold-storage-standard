"""Cleanup manager for temporary resources - ensures cleanup on signal interruption."""

import atexit
import signal
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from coldstore.logging import log_detail, log_info, log_warning


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
        """Clean up all registered temporary directories."""
        import shutil

        with self._lock:
            directories_to_clean = list(self._temp_directories)
            self._temp_directories.clear()

        for temp_dir in directories_to_clean:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    log_detail(f"Cleaned up temp directory: {temp_dir}")
            except OSError as e:
                log_warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

    def cleanup_temp_files(self):
        """Clean up all registered temporary files."""
        with self._lock:
            files_to_clean = list(self._temp_files)
            self._temp_files.clear()

        for temp_file in files_to_clean:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    log_detail(f"Cleaned up temp file: {temp_file}")
            except OSError as e:
                log_warning(f"Failed to cleanup temp file {temp_file}: {e}")

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

        # Clean up orphaned items
        for orphaned_dir in orphaned_dirs:
            try:
                import shutil

                shutil.rmtree(orphaned_dir)
                log_detail(f"Cleaned up orphaned temp directory: {orphaned_dir}")
            except OSError:
                pass

        for orphaned_file in orphaned_files:
            try:
                orphaned_file.unlink()
                log_detail(f"Cleaned up orphaned temp file: {orphaned_file}")
            except OSError:
                pass

        if orphaned_dirs or orphaned_files:
            log_info(
                f"Cleaned up {len(orphaned_dirs)} orphaned directories and {len(orphaned_files)} orphaned files"
            )


# Global cleanup manager instance
_cleanup_manager = None
_manager_lock = threading.Lock()


def get_cleanup_manager() -> CleanupManager:
    """Get the global cleanup manager instance."""
    global _cleanup_manager

    if _cleanup_manager is None:
        with _manager_lock:
            if _cleanup_manager is None:
                _cleanup_manager = CleanupManager()
                _cleanup_manager.register_signal_handlers()
                # Clean up any orphaned temps from previous runs
                _cleanup_manager.cleanup_orphaned_temps()

    return _cleanup_manager


def create_managed_temp_dir(prefix: str = "coldstore_") -> Path:
    """Create a temporary directory that will be automatically cleaned up."""
    manager = get_cleanup_manager()
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
    return manager.add_temp_directory(temp_dir)


def create_managed_temp_file(prefix: str = "coldstore_", suffix: str = "") -> Path:
    """Create a temporary file that will be automatically cleaned up."""
    manager = get_cleanup_manager()
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as tmp:
        temp_file = Path(tmp.name)
    return manager.add_temp_file(temp_file)


def register_cleanup_callback(callback: Callable[[], None]):
    """Register a custom cleanup callback."""
    manager = get_cleanup_manager()
    manager.add_cleanup_callback(callback)


def manual_cleanup():
    """Manually trigger cleanup (useful for testing)."""
    manager = get_cleanup_manager()
    manager.cleanup_all()
