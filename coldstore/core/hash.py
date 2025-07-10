"""Hash generation for SHA-256 and BLAKE3."""

import hashlib
from pathlib import Path

import blake3

from coldstore.logging import log_detail, log_error, log_info, log_step, log_warning


class HashGenerator:
    """Generate and verify SHA-256 and BLAKE3 hashes."""

    def __init__(self):
        self.chunk_size = 8 * 1024 * 1024  # 8MB chunks for large files

    def generate_sha256(self, file_path: Path) -> str | None:
        """Generate SHA-256 hash of file."""
        try:
            log_step("Generating SHA-256 hash")

            sha256_hash = hashlib.sha256()

            with open(file_path, "rb") as f:
                while chunk := f.read(self.chunk_size):
                    sha256_hash.update(chunk)

            hash_value = sha256_hash.hexdigest()
            log_info(f"SHA-256: {hash_value}")

            return hash_value

        except Exception as e:
            log_error(f"Failed to generate SHA-256 hash: {e}")
            return None

    def generate_blake3(self, file_path: Path) -> str | None:
        """Generate BLAKE3 hash of file."""
        try:
            log_step("Generating BLAKE3 hash")

            blake3_hash = blake3.blake3()

            with open(file_path, "rb") as f:
                while chunk := f.read(self.chunk_size):
                    blake3_hash.update(chunk)

            hash_value = blake3_hash.hexdigest()
            log_info(f"BLAKE3: {hash_value}")

            return hash_value

        except Exception as e:
            log_error(f"Failed to generate BLAKE3 hash: {e}")
            return None

    def generate_all_hashes(self, file_path: Path) -> dict[str, str | None]:
        """Generate both SHA-256 and BLAKE3 hashes."""
        log_info(f"Generating hashes for: {file_path.name}")

        return {
            "sha256": self.generate_sha256(file_path),
            "blake3": self.generate_blake3(file_path),
        }

    def save_hash_file(
        self, hash_value: str, hash_file_path: Path, original_filename: str
    ) -> bool:
        """Save hash to file in standard format."""
        try:
            with open(hash_file_path, "w") as f:
                f.write(f"{hash_value}  {original_filename}\n")

            log_detail(f"Hash saved to: {hash_file_path.name}")
            return True

        except Exception as e:
            log_error(f"Failed to save hash file {hash_file_path}: {e}")
            return False

    def save_all_hash_files(
        self, hashes: dict[str, str | None], base_file_path: Path
    ) -> dict[str, bool]:
        """Save both hash files."""
        results = {}
        original_filename = base_file_path.name

        # Save SHA-256 hash
        if hashes["sha256"]:
            sha256_file = base_file_path.with_suffix(base_file_path.suffix + ".sha256")
            results["sha256"] = self.save_hash_file(
                hashes["sha256"], sha256_file, original_filename
            )
        else:
            results["sha256"] = False

        # Save BLAKE3 hash
        if hashes["blake3"]:
            blake3_file = base_file_path.with_suffix(base_file_path.suffix + ".blake3")
            results["blake3"] = self.save_hash_file(
                hashes["blake3"], blake3_file, original_filename
            )
        else:
            results["blake3"] = False

        return results

    def verify_hash_file(self, hash_file_path: Path, target_file_path: Path) -> bool:
        """Verify hash file against target file."""
        try:
            # Read expected hash
            with open(hash_file_path) as f:
                line = f.readline().strip()
                if "  " in line:
                    expected_hash, filename = line.split("  ", 1)
                else:
                    expected_hash = line.split()[0] if line else ""

            if not expected_hash:
                log_error(f"Invalid hash file format: {hash_file_path}")
                return False

            # Determine hash type and generate actual hash
            if hash_file_path.suffix == ".sha256":
                actual_hash = self.generate_sha256(target_file_path)
                hash_type = "SHA-256"
            elif hash_file_path.suffix == ".blake3":
                actual_hash = self.generate_blake3(target_file_path)
                hash_type = "BLAKE3"
            else:
                log_error(f"Unknown hash file type: {hash_file_path.suffix}")
                return False

            if actual_hash is None:
                return False

            # Compare hashes
            if actual_hash.lower() == expected_hash.lower():
                log_info(f"{hash_type} verification: PASS")
                return True
            else:
                log_error(f"{hash_type} verification: FAIL")
                log_detail(f"Expected: {expected_hash}")
                log_detail(f"Actual:   {actual_hash}")
                return False

        except Exception as e:
            log_error(f"Failed to verify hash file {hash_file_path}: {e}")
            return False

    def generate_and_save_hashes(self, file_path: Path) -> bool:
        """Generate and save both hash files for a file."""
        log_info(f"Generating integrity hashes for: {file_path.name}")

        # Generate hashes
        hashes = self.generate_all_hashes(file_path)

        # Check if both hashes were generated successfully
        if not hashes["sha256"] or not hashes["blake3"]:
            log_error("Failed to generate one or more hashes")
            return False

        # Save hash files
        save_results = self.save_all_hash_files(hashes, file_path)

        # Check if both files were saved successfully
        success = all(save_results.values())

        if success:
            log_info("Hash generation and saving completed successfully")
        else:
            log_error("Failed to save one or more hash files")

        return success

    def verify_all_hashes(self, base_file_path: Path) -> dict[str, bool]:
        """Verify all hash files for a given file."""
        results = {}

        # Check SHA-256
        sha256_file = base_file_path.with_suffix(base_file_path.suffix + ".sha256")
        if sha256_file.exists():
            results["sha256"] = self.verify_hash_file(sha256_file, base_file_path)
        else:
            results["sha256"] = False
            log_warning(f"SHA-256 hash file not found: {sha256_file}")

        # Check BLAKE3
        blake3_file = base_file_path.with_suffix(base_file_path.suffix + ".blake3")
        if blake3_file.exists():
            results["blake3"] = self.verify_hash_file(blake3_file, base_file_path)
        else:
            results["blake3"] = False
            log_warning(f"BLAKE3 hash file not found: {blake3_file}")

        return results


def create_hash_generator() -> HashGenerator:
    """Create a hash generator instance."""
    return HashGenerator()
