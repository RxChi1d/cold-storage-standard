"""Hash generation for SHA-256 and BLAKE3."""

import hashlib
from pathlib import Path

import blake3

from coldstore.logger import log_error, log_info, log_step, log_warning


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

    def verify_sha256(self, file_path: Path, expected_hash: str) -> bool:
        """Verify SHA-256 hash of file."""
        try:
            log_step("Verifying SHA-256 hash")

            actual_hash = self.generate_sha256(file_path)
            if actual_hash is None:
                return False

            if actual_hash.lower() == expected_hash.lower():
                log_info("SHA-256 hash verification: PASSED")
                return True
            else:
                log_error("SHA-256 hash verification: FAILED")
                log_error(f"Expected: {expected_hash}")
                log_error(f"Actual:   {actual_hash}")
                return False

        except Exception as e:
            log_error(f"SHA-256 hash verification failed: {e}")
            return False

    def verify_blake3(self, file_path: Path, expected_hash: str) -> bool:
        """Verify BLAKE3 hash of file."""
        try:
            log_step("Verifying BLAKE3 hash")

            actual_hash = self.generate_blake3(file_path)
            if actual_hash is None:
                return False

            if actual_hash.lower() == expected_hash.lower():
                log_info("BLAKE3 hash verification: PASSED")
                return True
            else:
                log_error("BLAKE3 hash verification: FAILED")
                log_error(f"Expected: {expected_hash}")
                log_error(f"Actual:   {actual_hash}")
                return False

        except Exception as e:
            log_error(f"BLAKE3 hash verification failed: {e}")
            return False

    def read_hash_file(self, hash_file_path: Path) -> str | None:
        """Read hash value from a hash file."""
        try:
            with open(hash_file_path) as f:
                content = f.read().strip()
                # Hash files typically contain: "hash_value  filename"
                # We want just the hash value
                hash_value = content.split()[0]
                return hash_value
        except Exception as e:
            log_error(f"Failed to read hash file {hash_file_path}: {e}")
            return None

    def verify_all_hashes(self, file_path: Path) -> dict[str, bool]:
        """Verify all hash files for the given archive."""
        log_info(f"Verifying hashes for: {file_path.name}")

        results = {}

        # Check SHA-256
        sha256_file = file_path.with_suffix(file_path.suffix + ".sha256")
        if sha256_file.exists():
            expected_sha256 = self.read_hash_file(sha256_file)
            if expected_sha256:
                results["sha256"] = self.verify_sha256(file_path, expected_sha256)
            else:
                log_error(f"Could not read SHA-256 hash file: {sha256_file}")
                results["sha256"] = False
        else:
            log_warning(f"SHA-256 hash file not found: {sha256_file}")
            results["sha256"] = None

        # Check BLAKE3
        blake3_file = file_path.with_suffix(file_path.suffix + ".blake3")
        if blake3_file.exists():
            expected_blake3 = self.read_hash_file(blake3_file)
            if expected_blake3:
                results["blake3"] = self.verify_blake3(file_path, expected_blake3)
            else:
                log_error(f"Could not read BLAKE3 hash file: {blake3_file}")
                results["blake3"] = False
        else:
            log_warning(f"BLAKE3 hash file not found: {blake3_file}")
            results["blake3"] = None

        return results

    def generate_and_save_hashes(self, file_path: Path) -> bool:
        """Generate and save both SHA-256 and BLAKE3 hashes."""
        try:
            log_info(f"Generating and saving hashes for: {file_path.name}")

            # Generate hashes
            hashes = self.generate_all_hashes(file_path)

            if hashes["sha256"] is None or hashes["blake3"] is None:
                log_error("Failed to generate one or more hashes")
                return False

            # Save SHA-256 hash
            sha256_file = file_path.with_suffix(file_path.suffix + ".sha256")
            with open(sha256_file, "w") as f:
                f.write(f"{hashes['sha256']}  {file_path.name}\n")
            log_info(f"SHA-256 hash saved to: {sha256_file}")

            # Save BLAKE3 hash
            blake3_file = file_path.with_suffix(file_path.suffix + ".blake3")
            with open(blake3_file, "w") as f:
                f.write(f"{hashes['blake3']}  {file_path.name}\n")
            log_info(f"BLAKE3 hash saved to: {blake3_file}")

            return True

        except Exception as e:
            log_error(f"Failed to save hashes: {e}")
            return False


def create_hash_generator() -> HashGenerator:
    """Create a hash generator instance."""
    return HashGenerator()
