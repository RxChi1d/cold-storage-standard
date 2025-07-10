# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **standardized cold storage solution** for research data and experimental results. The project converts various compressed formats (7z/zip/rar) to verified tar.zst archives designed for long-term data preservation.

### Core Architecture

The system consists of 4 main shell scripts that work together:

1. **archive-compress.sh** (v2.1) - Main conversion tool
   - Converts 7z → tar.zst with integrity protection
   - Creates deterministic tar archives (--sort=name)
   - Generates SHA-256 + BLAKE3 hashes + PAR2 recovery files
   - Implements 5-stage verification process

2. **verify-archive.sh** (v1.0) - Integrity verification
   - Verifies zstd, SHA-256, BLAKE3, PAR2, and tar content
   - Supports batch verification
   - Can verify directories or individual files

3. **extract-archive.sh** (v2.0) - Extraction tool
   - Two-stage extraction (zstd → tar)
   - Safe directory creation with overwrite protection
   - Basic post-extraction verification

4. **verify-and-extract.sh** (v1.0) - Combined workflow
   - Orchestrates verify-archive.sh + extract-archive.sh
   - Provides unified interface for safe extraction

### Key Features

- **Deterministic archives**: Uses `tar --sort=name` for reproducible builds
- **Multi-layer integrity**: SHA-256 + BLAKE3 + PAR2 (10% redundancy)
- **Long-term compatibility**: Standard formats (tar + zstd) for future accessibility
- **Intelligent organization**: Creates subdirectories to avoid file conflicts
- **Memory optimization**: Uses `--long=31` (2GB dictionary) for better compression

## Common Commands

### Basic Usage

```bash
# Convert 7z files to cold storage format
./archive-compress.sh [directory]

# Verify archive integrity
./verify-archive.sh file.tar.zst

# Extract with verification
./verify-and-extract.sh file.tar.zst

# Quick extraction (already verified)
./extract-archive.sh file.tar.zst
```

### Common Options

```bash
# High compression with custom output
./archive-compress.sh -l 22 -o /backup ~/archives

# Fast processing (lower compression)
./archive-compress.sh -l 12 -t 8 ~/archives

# Batch verify directory
./verify-archive.sh -d ./processed

# Extract to specific directory
./extract-archive.sh -o /tmp/restore archive.tar.zst
```

### Testing and Verification

The project doesn't use traditional unit tests. Instead, verification is built into the workflow:

```bash
# Test archive integrity (recommended before any operation)
./verify-archive.sh -v archive.tar.zst

# Test complete workflow
./verify-and-extract.sh --verify-only archive.tar.zst

# Batch integrity check
./verify-archive.sh -q -d /backup/archives
```

## System Requirements

### Required Tools
- `7z` (7zip) - Archive extraction
- `tar` with POSIX/GNU format support - Archive creation
- `zstd` - Compression/decompression
- `sha256sum` - SHA-256 hashing
- `b3sum` - BLAKE3 hashing
- `par2` - PAR2 recovery files
- `bc` - Mathematical calculations

### Installation
```bash
# Ubuntu/Debian
sudo apt update && apt install tar zstd par2cmdline b3sum 7zip-full

# macOS (Homebrew)
brew install zstd par2 b3sum p7zip

# CentOS/RHEL/Rocky Linux
sudo yum install tar zstd par2cmdline b3sum p7zip
```

## File Organization

### Input/Output Structure

```
project-root/
├── archive-compress.sh    # Main conversion tool
├── verify-archive.sh      # Integrity verification
├── extract-archive.sh     # Extraction tool
├── verify-and-extract.sh  # Combined workflow
└── processed/             # Default output directory
    └── filename/          # Organized by subdirectories
        ├── filename.tar.zst
        ├── filename.tar.zst.sha256
        ├── filename.tar.zst.blake3
        ├── filename.tar.zst.par2
        └── filename.tar.zst.vol000+xx.par2
```

### Generated Files

Each processed archive creates:
- `.tar.zst` - Main compressed archive
- `.tar.zst.sha256` - SHA-256 hash
- `.tar.zst.blake3` - BLAKE3 hash
- `.tar.zst.par2` - PAR2 main file
- `.tar.zst.vol*.par2` - PAR2 recovery files (10% redundancy)

## Development Notes

### Script Architecture
- All scripts use consistent color-coded logging
- Modular functions for reusability
- Comprehensive error handling with diagnostic information
- Memory and disk space checking
- Support for both flat and organized file structures

### Memory Considerations
- `--long=31` requires ~2.2GB RAM for compression
- Large files (>2GB) need additional processing time
- Recommend SSD for temp file operations

### Error Handling
- Each script provides detailed error diagnostics
- Failed operations preserve partial results for debugging
- PAR2 files enable recovery from corruption
- Multiple verification stages catch errors early

## Troubleshooting

### Common Issues

1. **Memory errors**: Use `--no-long` or reduce compression level
2. **Disk space**: Ensure 2-3x original file size available
3. **Permission errors**: Check script execute permissions with `chmod +x *.sh`
4. **PAR2 failures**: Try repair with `par2 repair filename.tar.zst.par2`

### Verification Workflow
Always verify integrity before extraction:
```bash
./verify-archive.sh -v archive.tar.zst
```

If verification fails, check:
1. File corruption (use PAR2 repair)
2. Incorrect compression parameters
3. Insufficient disk space during creation
4. Tool version compatibility
