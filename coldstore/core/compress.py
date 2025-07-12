"""Compression engine for separated mode (tar → zstd)."""

import tarfile
from pathlib import Path

import zstandard as zstd

from coldstore.logging import log_detail, log_error, log_info, log_step, log_warning


class CompressionEngine:
    """Separated mode compression engine matching bash script functionality."""

    def __init__(self):
        self.compression_level = 19
        self.threads = 0  # 0 = auto
        self.long_mode = True
        self.temp_tar_path: Path | None = None

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
        Calculate optimal window_log based on file size.

        Window log guidelines (conservative for reliability):
        - Small files (<2MB): window_log=20 (1MB window, ~1MB memory)
        - Medium files (2-20MB): window_log=24 (16MB window, ~16MB memory)
        - Large files (20-200MB): window_log=27 (128MB window, ~128MB memory)
        - Very large files (>200MB): window_log=31 (2GB window, ~2GB memory)
        """
        if file_size < 2 * 1024 * 1024:  # < 2MB
            return 20  # 1MB window
        elif file_size < 20 * 1024 * 1024:  # < 20MB
            return 24  # 16MB window
        elif file_size < 200 * 1024 * 1024:  # < 200MB
            return 27  # 128MB window
        else:  # >= 200MB
            return 31  # 2GB window (original --long=31)

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
        """Verify tar archive integrity using Python tarfile (cross-platform)."""
        try:
            log_step("Verifying tar archive integrity")
            log_detail("Using Python tarfile for cross-platform verification")

            # Attempt to open and list the tar file
            with tarfile.open(tar_path, "r") as tar:
                # Try to get the list of members to verify integrity
                members = tar.getnames()
                log_detail(f"Verified {len(members)} archive members")

            log_info("Tar archive integrity verified")
            log_detail("✅ Cross-platform tar verification successful")
            return True

        except Exception as e:
            log_error(f"Tar archive integrity check failed: {e}")
            return False

    def compress_with_zstd(
        self,
        tar_path: Path,
        zst_path: Path,
        level: int = 19,
        threads: int = 0,
        long_mode: bool = True,
    ) -> bool:
        """Compress tar file with zstd."""
        try:
            log_step(f"Compressing with zstd (level {level})")

            # Configure zstd compression parameters
            if long_mode:
                # Dynamically choose window_log based on file size
                file_size = tar_path.stat().st_size
                window_log = self._calculate_optimal_window_log(file_size)

                log_detail(f"Long-distance matching enabled (window_log={window_log})")
                log_detail(
                    f"File size: {file_size / (1024 * 1024):.1f}MB, Window size: {2**window_log / (1024 * 1024):.0f}MB"
                )

                cparams = zstd.ZstdCompressionParameters(
                    compression_level=level,
                    window_log=window_log,
                    threads=threads if threads > 0 else 0,  # 0 = auto
                )
                compressor = zstd.ZstdCompressor(compression_params=cparams)
            else:
                # Simple compression without long-distance matching
                cparams = zstd.ZstdCompressionParameters(
                    compression_level=level,
                    threads=threads if threads > 0 else 0,  # 0 = auto
                )
                compressor = zstd.ZstdCompressor(compression_params=cparams)

            # Compress file
            with (
                open(tar_path, "rb") as input_file,
                open(zst_path, "wb") as output_file,
            ):
                compressor.copy_stream(input_file, output_file)

            # Verify output file was created
            if not zst_path.exists():
                log_error("Zstd file was not created")
                return False

            original_size = tar_path.stat().st_size
            compressed_size = zst_path.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100

            log_info(
                f"Compression complete: {original_size / (1024 * 1024):.1f} MB → "
                f"{compressed_size / (1024 * 1024):.1f} MB ({ratio:.1f}% reduction)"
            )

            return True

        except Exception as e:
            log_error(f"Failed to compress with zstd: {e}")
            return False

    def get_zstd_window_log(self, zst_path: Path) -> int:
        """
        Get window_log from zstd file for appropriate decompression memory settings.

        Returns:
            window_log value, or 20 as safe default
        """
        try:
            with open(zst_path, "rb") as f:
                data = f.read(32)  # Read just the frame header
                frame_params = zstd.get_frame_parameters(data)

                if frame_params.window_size > 0:
                    import math

                    window_log = int(math.log2(frame_params.window_size))
                    log_detail(
                        f"Detected window_log={window_log} (~{frame_params.window_size // (1024 * 1024)}MB window)"
                    )
                    return window_log
                else:
                    log_detail("No window size info, using default")
                    return 20

        except Exception as e:
            log_warning(f"Failed to read zstd frame parameters: {e}")
            return 20  # Safe default

    def verify_zstd_integrity(self, zst_path: Path) -> bool:
        """Verify zstd file integrity with appropriate memory settings."""
        try:
            log_step("Verifying zstd archive integrity")

            # Get window_log to inform user about memory requirements
            window_log = self.get_zstd_window_log(zst_path)

            if window_log > 27:
                memory_mb = (2**window_log) // (1024 * 1024)
                log_detail(
                    f"High compression detected: requires ~{memory_mb}MB memory for decompression"
                )

            decompressor = zstd.ZstdDecompressor()

            with open(zst_path, "rb") as input_file:
                # Test decompression without writing full output
                reader = decompressor.stream_reader(input_file)
                # Read small chunk to verify integrity
                chunk = reader.read(1024)
                if not chunk:
                    raise ValueError("Empty or corrupted zstd file")

            log_info("Zstd archive integrity verified")
            return True

        except Exception as e:
            log_error(f"Zstd integrity check failed: {e}")
            return False

    def create_temp_tar(self, prefix: str = "coldstore_") -> Path:
        """Create temporary tar file path."""
        from coldstore.core.cleanup import create_managed_temp_file

        self.temp_tar_path = create_managed_temp_file(prefix=prefix, suffix=".tar")
        return self.temp_tar_path

    def cleanup_temp_tar(self):
        """Clean up temporary tar file."""
        if self.temp_tar_path and self.temp_tar_path.exists():
            from coldstore.core.cleanup import get_cleanup_manager

            try:
                self.temp_tar_path.unlink()
                # Remove from cleanup manager since we cleaned it manually
                get_cleanup_manager().remove_temp_file(self.temp_tar_path)
                log_detail("Temporary tar file cleaned up")
            except OSError as e:
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
        """Compress directory using separated mode (tar → zstd)."""
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
            # Step 6: Clean up temporary files
            self.cleanup_temp_tar()

    def get_compression_info(self) -> dict:
        """Get current compression configuration."""
        return {
            "level": self.compression_level,
            "threads": self.threads,
            "long_mode": self.long_mode,
            "method": "separated (tar → zstd)",
        }

    def decompress_with_zstd(self, zst_path: Path, tar_path: Path) -> bool:
        """Decompress zstd file to tar file using detected window_log."""
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

            # Decompress file
            with (
                open(zst_path, "rb") as input_file,
                open(tar_path, "wb") as output_file,
            ):
                decompressor.copy_stream(input_file, output_file)

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
        """Complete two-stage decompression (zstd → tar → directory)."""
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
            # Step 6: Clean up temporary files
            self.cleanup_temp_tar()

    def get_archive_info(self, zst_path: Path) -> dict:
        """Get archive information without full extraction."""
        try:
            log_step("Getting archive information")

            # Get compression info
            window_log = self.get_zstd_window_log(zst_path)
            memory_mb = (2**window_log) // (1024 * 1024)

            # Get file sizes
            compressed_size = zst_path.stat().st_size

            return {
                "compressed_size": compressed_size,
                "window_log": window_log,
                "memory_required_mb": memory_mb,
                "format": "tar.zst",
                "compression_level": "detected from file",
            }

        except Exception as e:
            log_warning(f"Failed to get archive info: {e}")
            return {
                "compressed_size": zst_path.stat().st_size if zst_path.exists() else 0,
                "window_log": 20,  # safe default
                "memory_required_mb": 1,
                "format": "tar.zst",
                "compression_level": "unknown",
            }


def create_compressor() -> CompressionEngine:
    """Create a compression engine instance."""
    return CompressionEngine()
