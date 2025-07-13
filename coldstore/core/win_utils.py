"""Windows-specific utilities for file handling and process management."""

import platform
import subprocess
import time
from pathlib import Path

from coldstore.logger import log_detail, log_warning


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def get_file_handles(file_path: Path) -> list[dict]:
    """
    Get list of processes holding handles to a file on Windows.

    Args:
        file_path: Path to the file

    Returns:
        List of dictionaries with process information
    """
    if not is_windows():
        return []

    handles = []
    try:
        # Use handle.exe from SysInternals if available
        result = subprocess.run(
            ["handle.exe", "-u", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if str(file_path).lower() in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        handles.append(
                            {
                                "process": parts[0],
                                "pid": parts[1] if parts[1].isdigit() else None,
                                "line": line.strip(),
                            }
                        )
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        # handle.exe not available or failed
        pass

    return handles


def force_close_file_handles(file_path: Path) -> bool:
    """
    Force close file handles on Windows using system tools.

    Args:
        file_path: Path to the file

    Returns:
        True if successful, False otherwise
    """
    if not is_windows():
        return False

    try:
        # Try using handle.exe to close handles
        result = subprocess.run(
            ["handle.exe", "-c", str(file_path), "-y"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            log_detail(f"Successfully closed file handles for: {file_path}")
            return True

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass

    return False


def kill_processes_using_file(file_path: Path) -> bool:
    """
    Kill processes that are using a file on Windows.

    Args:
        file_path: Path to the file

    Returns:
        True if any processes were killed, False otherwise
    """
    if not is_windows():
        return False

    killed_any = False

    try:
        # Use wmic to find processes using the file
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                f"ExecutablePath like '%{file_path.name}%'",
                "get",
                "ProcessId",
                "/format:csv",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines[1:]:  # Skip header
                if line.strip():
                    parts = line.split(",")
                    if len(parts) >= 2 and parts[1].strip().isdigit():
                        pid = parts[1].strip()
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                capture_output=True,
                                timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                            log_detail(f"Killed process {pid} using file {file_path}")
                            killed_any = True
                        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                            pass

    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass

    return killed_any


def unlock_file_windows(file_path: Path) -> bool:
    """
    Attempt to unlock a file on Windows using various methods.

    Args:
        file_path: Path to the file to unlock

    Returns:
        True if file was unlocked, False otherwise
    """
    if not is_windows() or not file_path.exists():
        return False

    log_detail(f"Attempting to unlock file: {file_path}")

    # Method 1: Try to remove read-only attribute
    try:
        import stat

        current_mode = file_path.stat().st_mode
        if not (current_mode & stat.S_IWRITE):
            file_path.chmod(current_mode | stat.S_IWRITE)
            log_detail("Removed read-only attribute")
    except (OSError, PermissionError):
        pass

    # Method 2: Try to close file handles
    if force_close_file_handles(file_path):
        time.sleep(0.1)
        if not file_path.exists():
            return True

    # Method 3: As last resort, try to kill processes
    # Only do this for temporary files to avoid data loss
    if (
        "temp" in str(file_path).lower() or "coldstore_" in file_path.name
    ) and kill_processes_using_file(file_path):
        time.sleep(0.2)
        if not file_path.exists():
            return True

    return False


def windows_safe_remove(file_path: Path, max_retries: int = 8) -> bool:
    """
    Windows-safe file removal with aggressive retry logic.

    Args:
        file_path: Path to the file to remove
        max_retries: Maximum number of retry attempts

    Returns:
        True if successfully removed, False otherwise
    """
    if not is_windows():
        return False

    for attempt in range(max_retries):
        try:
            if not file_path.exists():
                return True

            # Try normal removal first
            file_path.unlink()
            return True

        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                log_detail(f"Windows file removal attempt {attempt + 1} failed: {e}")

                # Progressive retry strategy
                if attempt == 0:
                    # First retry: just wait
                    time.sleep(0.5)
                elif attempt == 1:
                    # Second retry: remove read-only and wait
                    try:
                        import stat

                        file_path.chmod(stat.S_IWRITE)
                    except (OSError, PermissionError):
                        pass
                    time.sleep(1.0)
                elif attempt == 2:
                    # Third retry: try to unlock file
                    unlock_file_windows(file_path)
                    time.sleep(1.5)
                elif attempt >= 3:
                    # Later retries: more aggressive unlocking with longer waits
                    unlock_file_windows(file_path)
                    time.sleep(2.0 + (attempt - 3) * 0.5)

                continue
            else:
                log_warning(
                    f"Failed to remove file {file_path} after {max_retries} attempts: {e}"
                )
                return False

    return False


def windows_safe_rmdir(dir_path: Path, max_retries: int = 5) -> bool:
    """
    Windows-safe directory removal with retry logic.

    Args:
        dir_path: Path to the directory to remove
        max_retries: Maximum number of retry attempts

    Returns:
        True if successfully removed, False otherwise
    """
    if not is_windows():
        return False

    import shutil

    for attempt in range(max_retries):
        try:
            if not dir_path.exists():
                return True

            # Try normal removal first
            shutil.rmtree(dir_path)
            return True

        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                log_detail(
                    f"Windows directory removal attempt {attempt + 1} failed: {e}"
                )

                # Try to unlock files in directory
                try:
                    for file_path in dir_path.rglob("*"):
                        if file_path.is_file():
                            unlock_file_windows(file_path)
                except (OSError, PermissionError):
                    pass

                time.sleep(1.0 + attempt * 0.5)
                continue
            else:
                log_warning(
                    f"Failed to remove directory {dir_path} after {max_retries} attempts: {e}"
                )
                return False

    return False
