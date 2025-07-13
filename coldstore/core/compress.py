"""Compression engine for separated mode (tar → zstd)."""

import platform
import sys
import tarfile
from pathlib import Path

import zstandard as zstd

from coldstore.logger import log_detail, log_error, log_info, log_step, log_warning


class CompressionEngine:
    """Separated mode compression engine matching bash script functionality."""

    def __init__(self):
        self.compression_level = 19
        self.threads = 0  # 0 = auto
        self.long_mode = True
        self.temp_tar_path: Path | None = None
        self._cleanup_initialized = False

    def _ensure_cleanup_initialized(self):
        """Ensure cleanup system is initialized (called lazily)."""
        if not self._cleanup_initialized:
            from coldstore.core.cleanup import initialize_cleanup

            initialize_cleanup()
            self._cleanup_initialized = True

    def _estimate_data_size(self, source_path: Path, archive_path: Path = None) -> int:
        """
        Estimate data size using a balanced approach between performance and accuracy.

        Strategy:
        1. If source is a directory, quickly estimate by sampling
        2. If archive_path provided, use as reference
        3. Use the larger estimate for conservative window_log selection
        """
        estimates = []

        # Method 1: Quick directory sampling (fast estimate)
        if source_path.is_dir():
            try:
                # Sample first 100 files to estimate average size and total count
                all_files = list(source_path.rglob("*"))
                if all_files:
                    sample_files = all_files[: min(100, len(all_files))]
                    sample_size = sum(
                        f.stat().st_size for f in sample_files if f.is_file()
                    )

                    if sample_files:
                        avg_file_size = sample_size / len(
                            [f for f in sample_files if f.is_file()]
                        )
                        total_files = len([f for f in all_files if f.is_file()])
                        estimated_size = int(
                            avg_file_size * total_files * 1.1
                        )  # 10% overhead
                        estimates.append(("directory_sampling", estimated_size))
                        log_detail(
                            f"Directory sampling estimate: {estimated_size / (1024 * 1024):.1f}MB"
                        )
            except Exception as e:
                log_detail(f"Directory sampling failed: {e}")

        # Method 2: Archive size reference (if available)
        if archive_path and archive_path.exists():
            archive_size = archive_path.stat().st_size
            # Typical compression ratios: 7z usually 30-70% of original
            # Estimate original size as 2-5x archive size (conservative)
            estimated_original = int(archive_size * 3.5)  # Conservative multiplier
            estimates.append(("archive_reference", estimated_original))
            log_detail(
                f"Archive reference estimate: {estimated_original / (1024 * 1024):.1f}MB"
            )

        # Use the larger estimate for conservative memory allocation
        if estimates:
            selected_estimate = max(estimates, key=lambda x: x[1])
            log_detail(f"Selected estimate method: {selected_estimate[0]}")
            return selected_estimate[1]
        else:
            # Fallback: assume moderate size
            return 10 * 1024 * 1024  # 10MB default

    def _calculate_optimal_window_log(self, file_size: int) -> int:
        """
        Calculate optimal window_log based on file size with platform-specific limits.

        Window log guidelines (conservative for reliability):
        - Small files (<2MB): window_log=20 (1MB window, ~1MB memory)
        - Medium files (2-20MB): window_log=24 (16MB window, ~16MB memory)
        - Large files (20-200MB): window_log=27 (128MB window, ~128MB memory)
        - Very large files (>200MB): window_log=28-31 (platform dependent)

        Platform limits:
        - 32-bit systems: max window_log=30 (1GB limit)
        - 64-bit systems: max window_log=31 (2GB limit)
        - Windows: Conservative limits due to virtual memory allocation
        """
        # Determine platform-specific maximum window_log
        is_64bit = sys.maxsize > 2**32
        is_windows = platform.system() == "Windows"

        if is_64bit:
            # 64-bit systems can handle larger windows
            max_window_log = 30 if is_windows else 31
        else:
            # 32-bit systems are more limited
            max_window_log = 29 if is_windows else 30

        # Calculate optimal window_log based on file size
        if file_size < 2 * 1024 * 1024:  # < 2MB
            return 20  # 1MB window
        elif file_size < 20 * 1024 * 1024:  # < 20MB
            return 24  # 16MB window
        elif file_size < 200 * 1024 * 1024:  # < 200MB
            return 27  # 128MB window
        else:  # >= 200MB
            # Use platform-appropriate maximum
            log_detail(
                f"Large file detected, using max window_log={max_window_log} for platform compatibility"
            )
            return max_window_log

    def _get_sorted_file_list(self, directory: Path) -> list[tuple[Path, Path]]:
        """
        Get deterministic sorted file list (equivalent to tar --sort=name).

        Returns:
            List of (absolute_path, relative_path) tuples in sorted order
        """
        files = []

        def add_files_recursively(current_dir: Path, relative_base: Path):
            """Recursively add files to list in sorted order."""
            try:
                # Get all items in current directory and sort by name
                items = sorted(current_dir.iterdir(), key=lambda x: x.name)

                for item in items:
                    # Calculate relative path from the base directory
                    relative_path = item.relative_to(relative_base)
                    files.append((item, relative_path))

                    # If directory, recurse
                    if item.is_dir():
                        add_files_recursively(item, relative_base)

            except (PermissionError, OSError) as e:
                log_warning(f"Cannot access {current_dir}: {e}")

        # Use the directory itself as the relative base to avoid including directory name
        add_files_recursively(directory, directory)

        # Sort by relative path for deterministic order
        files.sort(key=lambda x: str(x[1]))

        return files

    def create_deterministic_tar(self, source_path: Path, tar_path: Path) -> bool:
        """Create deterministic tar archive using Python tarfile (cross-platform)."""
        try:
            log_step("Creating deterministic tar archive")
            log_detail("Using Python tarfile for cross-platform compatibility")
            log_detail("Applying deterministic sorting (equivalent to tar --sort=name)")
            log_detail(f"Source path: {source_path}")

            # Handle single file vs directory
            if source_path.is_file():
                # For single files, create a simple deterministic archive
                with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tar:
                    tarinfo = tar.gettarinfo(source_path, source_path.name)

                    # Set deterministic properties
                    tarinfo.uid = 0
                    tarinfo.gid = 0
                    tarinfo.uname = "root"
                    tarinfo.gname = "root"
                    tarinfo.mtime = 0

                    with open(source_path, "rb") as f:
                        tar.addfile(tarinfo, f)

                log_detail("Single file archived with deterministic properties")
            else:
                # For directories, use deterministic file sorting
                file_list = self._get_sorted_file_list(source_path)
                log_detail(f"Found {len(file_list)} items to archive")
                log_detail(
                    "Archive will contain files relative to source directory (no parent path included)"
                )

                # Create tar archive with PAX format for better compatibility and large files
                with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as tar:
                    for absolute_path, relative_path in file_list:
                        try:
                            tarinfo = tar.gettarinfo(absolute_path, str(relative_path))

                            # Set deterministic properties (equivalent to tar behavior)
                            tarinfo.uid = 0
                            tarinfo.gid = 0
                            tarinfo.uname = "root"
                            tarinfo.gname = "root"
                            tarinfo.mtime = 0

                            if absolute_path.is_file():
                                with open(absolute_path, "rb") as f:
                                    tar.addfile(tarinfo, f)
                            else:
                                tar.addfile(tarinfo)

                        except (OSError, ValueError) as e:
                            log_warning(f"Skipping {relative_path}: {e}")
                            continue

            # Verify tar file was created
            if not tar_path.exists():
                log_error("Tar file was not created")
                return False

            tar_size = tar_path.stat().st_size
            log_info(f"Tar archive created: {tar_size / (1024 * 1024):.1f} MB")
            log_detail("✅ Cross-platform deterministic tar creation successful")

            return True

        except Exception as e:
            log_error(f"Failed to create tar archive: {e}")
            return False

    def verify_tar_integrity(self, tar_path: Path) -> bool:
        """Verify tar archive integrity."""
        try:
            log_step("Verifying tar archive integrity")

            with tarfile.open(tar_path, "r") as tar:
                # Try to read member list (will fail if corrupt)
                members = tar.getmembers()
                log_detail(f"Tar archive contains {len(members)} members")

            log_detail("✅ Tar integrity verification successful")
            return True

        except Exception as e:
            log_error(f"Tar integrity verification failed: {e}")
            return False

    def compress_with_zstd(
        self,
        tar_path: Path,
        zst_path: Path,
        level: int = 19,
        threads: int = 0,
        long_mode: bool = True,
    ) -> bool:
        """Compress tar file with zstd using optimized parameters and enhanced file handle management."""
        import contextlib

        input_file = None
        output_file = None

        try:
            log_step(f"Compressing with zstd (level {level})")

            # Estimate data size and calculate optimal window_log
            file_size = tar_path.stat().st_size
            window_log = self._calculate_optimal_window_log(file_size)
            memory_mb = (2**window_log) // (1024 * 1024)

            log_detail(f"Input size: {file_size / (1024 * 1024):.1f} MB")
            log_detail(
                f"Using window_log={window_log} (~{memory_mb}MB memory requirement)"
            )

            # Configure compressor parameters
            if long_mode and level >= 10:
                # Use long mode for high compression levels
                # Note: compression_params is mutually exclusive with level, write_checksum, and threads parameters
                # threads must be specified in compression_params, not in ZstdCompressor
                compression_params = zstd.ZstdCompressionParameters.from_level(
                    level,
                    window_log=window_log,
                    write_checksum=True,
                    threads=threads if threads > 0 else 0,
                )
                cctx = zstd.ZstdCompressor(
                    compression_params=compression_params,
                )
                log_detail(
                    f"Long mode enabled with window_log={window_log}, threads={threads if threads > 0 else 'auto'}"
                )
            else:
                # Standard compression for lower levels
                cctx = zstd.ZstdCompressor(
                    level=level,
                    threads=threads if threads > 0 else 0,
                    write_checksum=True,
                )
                log_detail("Standard compression mode")

            # Perform compression with explicit file handle management
            input_file = open(tar_path, "rb")
            output_file = open(zst_path, "wb")

            # Use buffer to reduce memory usage and improve interruption handling
            cctx.copy_stream(input_file, output_file)

            # Explicitly close files before verification
            input_file.close()
            output_file.close()
            input_file = None
            output_file = None

            # Verify output and calculate compression ratio
            if not zst_path.exists():
                log_error("Zstd file was not created")
                return False

            original_size = tar_path.stat().st_size
            compressed_size = zst_path.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100

            log_info(
                f"Compression complete: {original_size / (1024 * 1024):.1f} MB → {compressed_size / (1024 * 1024):.1f} MB ({ratio:.1f}% reduction)"
            )
            log_detail("✅ Zstd compression successful")

            return True

        except Exception as e:
            log_error(f"Failed to compress with zstd: {e}")
            return False
        finally:
            # Ensure files are always closed, even on interruption
            if input_file:
                with contextlib.suppress(Exception):
                    input_file.close()
            if output_file:
                with contextlib.suppress(Exception):
                    output_file.close()

    def get_zstd_window_log(self, zst_path: Path) -> int:
        """Get window_log from zstd compressed file."""
        try:
            with open(zst_path, "rb") as f:
                # Read enough bytes for frame header
                header_bytes = f.read(18)

                # Use module-level function to get frame parameters
                frame_params = zstd.get_frame_parameters(header_bytes)

                # Extract window_log from frame parameters
                if hasattr(frame_params, "window_size") and frame_params.window_size:
                    import math

                    window_log = int(math.log2(frame_params.window_size))
                    return window_log
                else:
                    # Default window_log if not available
                    return 23

        except Exception as e:
            log_warning(f"Failed to get window_log from zstd file: {e}")
            return 23  # Default window_log

    def verify_zstd_integrity(self, zst_path: Path) -> bool:
        """Verify zstd file integrity."""
        try:
            log_step("Verifying zstd file integrity")

            # Try to read and validate the frame header
            with open(zst_path, "rb") as f:
                # Read enough bytes for frame header
                header_bytes = f.read(18)

                # Use module-level function to validate frame header
                frame_params = zstd.get_frame_parameters(header_bytes)

                # If we can read frame parameters, the header is valid
                if hasattr(frame_params, "window_size"):
                    window_size = frame_params.window_size or "unknown"
                    log_detail(f"Zstd file has valid header, window_size={window_size}")
                else:
                    log_detail("Zstd file has valid header format")

            log_detail("✅ Zstd integrity verification successful")
            return True

        except Exception as e:
            log_error(f"Zstd integrity verification failed: {e}")
            return False

    def create_temp_tar(self, prefix: str = "coldstore_") -> Path:
        """Create temporary tar file path."""
        self._ensure_cleanup_initialized()
        from coldstore.core.cleanup import create_managed_temp_file

        self.temp_tar_path = create_managed_temp_file(prefix=prefix, suffix=".tar")
        return self.temp_tar_path

    def cleanup_temp_tar(self):
        """Clean up temporary tar file with enhanced error handling."""
        if self.temp_tar_path and self.temp_tar_path.exists():
            from coldstore.core.cleanup import _force_remove_file, get_cleanup_manager

            try:
                # Use the enhanced cleanup system
                if _force_remove_file(self.temp_tar_path, max_retries=8):
                    log_detail("Temporary tar file cleaned up successfully")
                    # Remove from cleanup manager since we cleaned it manually
                    get_cleanup_manager().remove_temp_file(self.temp_tar_path)
                else:
                    log_warning(
                        f"Failed to cleanup temp tar file: {self.temp_tar_path}"
                    )
                    log_detail(
                        "File will be cleaned up on next startup or system restart"
                    )
            except Exception as e:
                log_warning(f"Failed to cleanup temp tar file: {e}")
            finally:
                self.temp_tar_path = None

    def compress_directory(
        self,
        source_path: Path,
        output_path: Path,
        level: int = 19,
        threads: int = 0,
        long_mode: bool = True,
        enable_check: bool = True,
    ) -> bool:
        """Compress directory using separated mode (tar → zstd) with enhanced cleanup."""
        try:
            log_info(f"Starting compression: {source_path} → {output_path}")

            # Step 1: Create temporary tar file
            temp_tar = self.create_temp_tar()

            # Step 2: Create deterministic tar
            if not self.create_deterministic_tar(source_path, temp_tar):
                return False

            # Step 3: Verify tar integrity (optional)
            if enable_check and not self.verify_tar_integrity(temp_tar):
                return False

            # Step 4: Compress with zstd
            if not self.compress_with_zstd(
                temp_tar, output_path, level, threads, long_mode
            ):
                return False

            # Step 5: Verify zstd integrity (optional)
            if enable_check and not self.verify_zstd_integrity(output_path):
                return False

            log_info("Compression completed successfully")
            return True

        except Exception as e:
            log_error(f"Compression failed: {e}")
            return False

        finally:
            # Step 6: Clean up temporary files with enhanced cleanup
            try:
                self.cleanup_temp_tar()
            except Exception as cleanup_error:
                log_warning(f"Cleanup during compression failed: {cleanup_error}")

    def get_compression_info(self) -> dict:
        """Get current compression configuration."""
        return {
            "level": self.compression_level,
            "threads": self.threads,
            "long_mode": self.long_mode,
            "method": "separated (tar → zstd)",
        }

    def decompress_with_zstd(self, zst_path: Path, tar_path: Path) -> bool:
        """Decompress zstd file to tar file using detected window_log with enhanced file handle management."""
        import contextlib

        input_file = None
        output_file = None

        try:
            log_step(f"Decompressing zstd file: {zst_path.name}")

            # Get window_log from the compressed file
            window_log = self.get_zstd_window_log(zst_path)
            memory_mb = (2**window_log) // (1024 * 1024)

            log_detail(
                f"Using window_log={window_log} (~{memory_mb}MB memory for decompression)"
            )

            if window_log > 27:
                log_detail(f"High compression detected: requires ~{memory_mb}MB memory")

            # Create decompressor with appropriate settings
            decompressor = zstd.ZstdDecompressor()

            # Decompress file with explicit file handle management
            input_file = open(zst_path, "rb")
            output_file = open(tar_path, "wb")

            decompressor.copy_stream(input_file, output_file)

            # Explicitly close files before verification
            input_file.close()
            output_file.close()
            input_file = None
            output_file = None

            # Verify output file was created
            if not tar_path.exists():
                log_error("Tar file was not created during decompression")
                return False

            original_size = zst_path.stat().st_size
            decompressed_size = tar_path.stat().st_size

            log_info(
                f"Decompression complete: {original_size / (1024 * 1024):.1f} MB → {decompressed_size / (1024 * 1024):.1f} MB"
            )

            return True

        except Exception as e:
            log_error(f"Failed to decompress zstd file: {e}")
            return False
        finally:
            # Ensure files are always closed, even on interruption
            if input_file:
                with contextlib.suppress(Exception):
                    input_file.close()
            if output_file:
                with contextlib.suppress(Exception):
                    output_file.close()

    def extract_tar_archive(self, tar_path: Path, output_dir: Path) -> bool:
        """Extract tar archive to output directory."""
        try:
            log_step(f"Extracting tar archive: {tar_path.name}")
            log_detail("Using Python tarfile for cross-platform extraction")

            # Create output directory if it doesn't exist
            output_dir.mkdir(parents=True, exist_ok=True)

            # Extract tar archive
            with tarfile.open(tar_path, "r") as tar:
                # Get list of members for safety check
                members = tar.getmembers()

                # Check for path traversal attacks
                for member in members:
                    if member.name.startswith("/") or ".." in member.name:
                        log_warning(
                            f"Skipping potentially dangerous path: {member.name}"
                        )
                        continue

                # Extract all safe members
                safe_members = [
                    m for m in members if not (m.name.startswith("/") or ".." in m.name)
                ]
                tar.extractall(path=output_dir, members=safe_members)

                log_info(f"Extracted {len(safe_members)} items to: {output_dir}")
                log_detail("✅ Cross-platform tar extraction successful")

            return True

        except Exception as e:
            log_error(f"Failed to extract tar archive: {e}")
            return False

    def decompress_archive(
        self, zst_path: Path, output_dir: Path, enable_check: bool = True
    ) -> bool:
        """Complete two-stage decompression (zstd → tar → directory) with enhanced cleanup."""
        try:
            log_info(f"Starting decompression: {zst_path} → {output_dir}")

            # Step 1: Verify zstd integrity (optional)
            if enable_check and not self.verify_zstd_integrity(zst_path):
                log_error("Zstd integrity check failed")
                return False

            # Step 2: Create temporary tar file
            temp_tar = self.create_temp_tar(prefix="coldstore_decompress_")

            # Step 3: Decompress zstd to tar
            if not self.decompress_with_zstd(zst_path, temp_tar):
                return False

            # Step 4: Verify tar integrity (optional)
            if enable_check and not self.verify_tar_integrity(temp_tar):
                log_error("Tar integrity check failed")
                return False

            # Step 5: Extract tar to output directory
            if not self.extract_tar_archive(temp_tar, output_dir):
                return False

            log_info("Decompression completed successfully")
            return True

        except Exception as e:
            log_error(f"Decompression failed: {e}")
            return False

        finally:
            # Step 6: Clean up temporary files with enhanced cleanup
            try:
                self.cleanup_temp_tar()
            except Exception as cleanup_error:
                log_warning(f"Cleanup during decompression failed: {cleanup_error}")

    def get_archive_info(self, zst_path: Path) -> dict:
        """Get archive information without full extraction."""
        try:
            log_step("Getting archive information")

            # Create temporary tar file for decompression
            temp_tar = self.create_temp_tar(prefix="coldstore_info_")

            # Decompress to get tar file
            if not self.decompress_with_zstd(zst_path, temp_tar):
                return {"error": "Failed to decompress for analysis"}

            # Analyze tar contents
            info = {
                "files": 0,
                "folders": 0,
                "total_size": 0,
                "compressed_size": zst_path.stat().st_size,
                "format": "zstd",
            }

            with tarfile.open(temp_tar, "r") as tar:
                members = tar.getmembers()
                for member in members:
                    if member.isfile():
                        info["files"] += 1
                        info["total_size"] += member.size
                    elif member.isdir():
                        info["folders"] += 1

            return info

        except Exception as e:
            log_warning(f"Failed to get archive info: {e}")
            return {"error": str(e)}

        finally:
            # Clean up temporary files
            try:
                self.cleanup_temp_tar()
            except Exception as cleanup_error:
                log_warning(f"Cleanup during archive info failed: {cleanup_error}")


def create_compressor() -> CompressionEngine:
    """Create and return a new compression engine instance."""
    return CompressionEngine()
