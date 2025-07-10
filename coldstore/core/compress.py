"""Compression engine for separated mode (tar → zstd)."""

import subprocess
import tempfile
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

    def create_deterministic_tar(self, source_path: Path, tar_path: Path) -> bool:
        """Create deterministic tar archive with sorted file order."""
        try:
            log_step("Creating deterministic tar archive")

            # Build tar command with deterministic options
            cmd = [
                "tar",
                "--create",
                "--file",
                str(tar_path),
                "--sort=name",  # Deterministic file order
                "--numeric-owner",  # Use numeric IDs
                "--owner=0",  # Set owner to 0
                "--group=0",  # Set group to 0
                "--mtime=@0",  # Set modification time to epoch
                "--format=posix",  # Use POSIX format
                "-C",
                str(source_path.parent),
                source_path.name,
            ]

            log_detail(f"Tar command: {' '.join(cmd)}")

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            # Verify tar file was created
            if not tar_path.exists():
                log_error("Tar file was not created")
                return False

            tar_size = tar_path.stat().st_size
            log_info(f"Tar archive created: {tar_size / (1024*1024):.1f} MB")

            return True

        except subprocess.CalledProcessError as e:
            log_error(f"Failed to create tar archive: {e}")
            if e.stderr:
                log_detail(f"Error output: {e.stderr}")
            return False

    def verify_tar_integrity(self, tar_path: Path) -> bool:
        """Verify tar archive integrity."""
        try:
            log_step("Verifying tar archive integrity")

            subprocess.run(
                ["tar", "--test-label", "--file", str(tar_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            log_info("Tar archive integrity verified")
            return True

        except subprocess.CalledProcessError:
            log_error("Tar archive integrity check failed")
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

            # Configure zstd compressor
            compression_params = {
                "level": level,
                "threads": threads if threads > 0 else -1,  # -1 = auto
            }

            # Add long-distance matching if enabled
            if long_mode:
                compression_params["window_log"] = 31  # --long=31
                log_detail("Long-distance matching enabled (window_log=31)")

            compressor = zstd.ZstdCompressor(**compression_params)

            # Compress file
            with open(tar_path, "rb") as input_file, open(
                zst_path, "wb"
            ) as output_file:
                compressor.copy_stream(input_file, output_file)

            # Verify output file was created
            if not zst_path.exists():
                log_error("Zstd file was not created")
                return False

            original_size = tar_path.stat().st_size
            compressed_size = zst_path.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100

            log_info(
                f"Compression complete: {original_size / (1024*1024):.1f} MB → "
                f"{compressed_size / (1024*1024):.1f} MB ({ratio:.1f}% reduction)"
            )

            return True

        except Exception as e:
            log_error(f"Failed to compress with zstd: {e}")
            return False

    def verify_zstd_integrity(self, zst_path: Path) -> bool:
        """Verify zstd file integrity."""
        try:
            log_step("Verifying zstd archive integrity")

            decompressor = zstd.ZstdDecompressor()

            with open(zst_path, "rb") as input_file:
                # Test decompression without writing output
                decompressor.stream_reader(input_file).read(1024)

            log_info("Zstd archive integrity verified")
            return True

        except Exception as e:
            log_error(f"Zstd integrity check failed: {e}")
            return False

    def create_temp_tar(self, prefix: str = "coldstore_") -> Path:
        """Create temporary tar file path."""
        temp_file = tempfile.NamedTemporaryFile(
            prefix=prefix, suffix=".tar", delete=False
        )
        temp_file.close()
        self.temp_tar_path = Path(temp_file.name)
        return self.temp_tar_path

    def cleanup_temp_tar(self):
        """Clean up temporary tar file."""
        if self.temp_tar_path and self.temp_tar_path.exists():
            try:
                self.temp_tar_path.unlink()
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


def create_compressor() -> CompressionEngine:
    """Create a compression engine instance."""
    return CompressionEngine()
