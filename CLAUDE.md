# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **standardized cold storage solution** for research data and experimental results. The project converts various compressed formats (7z/zip/rar) to verified tar.zst archives designed for long-term data preservation.

### Current Development Status

**Milestone Progress:**
- ✅ **M0**: Python CLI baseline architecture
- ✅ **M1**: Core compression functionality (pack command)
- ✅ **M2**: Full decompression workflow (verify, extract, process commands)
- ⏳ **M3**: PAR2 repair functionality (next phase)

### Core Architecture

The system consists of **two implementations**:

#### 1. Python Application (coldstore) - **Primary Tool**
Modern Python CLI with intelligent compression and cross-platform compatibility:

- **pack** - Convert archives to cold storage format (replaces archive-compress.sh)
- **verify** - Multi-layer integrity verification (replaces verify-archive.sh)
- **extract** - Intelligent extraction with auto-detection (replaces extract-archive.sh)
- **process** - Combined verify+extract workflow (replaces verify-and-extract.sh)
- **repair** - PAR2 repair functionality (planned M3 feature)

**Key Features:**
- **Intelligent compression**: Auto-detects optimal window_log based on file size
- **Memory optimization**: Automatically adjusts memory usage (1MB to 2GB)
- **Cross-platform**: Pure Python implementation, no external dependencies
- **Rich UI**: Beautiful progress bars and system information displays
- **Smart extraction**: Auto-detects compression parameters for optimal decompression

#### 2. Shell Scripts (Legacy) - **Maintenance Mode**
Four bash scripts for backward compatibility:

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

### Primary Tool (coldstore)

**Installation:**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install system dependencies for hash/recovery operations
# Ubuntu/Debian
sudo apt update && apt install python3 par2cmdline b3sum

# macOS (Homebrew)
brew install python3 par2 b3sum

# CentOS/RHEL/Rocky Linux
sudo yum install python3 par2cmdline b3sum
```

**Basic Usage:**
```bash
# Convert archives to cold storage format
coldstore pack input_directory

# Verify archive integrity (5-layer verification)
coldstore verify archive.tar.zst

# Extract archives (with auto-detection)
coldstore extract archive.tar.zst

# Combined verify + extract workflow
coldstore process archive.tar.zst
```

**Advanced Options:**
```bash
# High compression with custom output
coldstore pack -l 22 -o /backup ~/archives

# Fast processing (lower compression)
coldstore pack -l 12 -t 8 ~/archives

# Batch verify directory
coldstore verify -d /backup/archives

# Extract to specific directory
coldstore extract -o /tmp/restore archive.tar.zst

# Force extraction (overwrite existing)
coldstore extract -f archive.tar.zst

# Verify only (no extraction)
coldstore process --verify-only archive.tar.zst
```

### Legacy Shell Scripts

**Basic Usage:**
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

**Common Options:**
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

**Python Application:**
```bash
# Multi-layer integrity verification
coldstore -v verify archive.tar.zst

# Batch verification with detailed output
coldstore -v verify -d /backup/archives

# Test complete workflow
coldstore process --verify-only archive.tar.zst
```

**Shell Scripts:**
```bash
# Test archive integrity
./verify-archive.sh -v archive.tar.zst

# Test complete workflow
./verify-and-extract.sh --verify-only archive.tar.zst

# Batch integrity check
./verify-archive.sh -q -d /backup/archives
```

## System Requirements

### For Python Application (coldstore) - **Recommended**

**Python Dependencies:**
- `python3` (3.8+) - Python runtime
- `py7zr` - Archive extraction (.7z, .zip, .tar, etc.)
- `python-zstandard` - Intelligent compression/decompression
- `tarfile` (built-in) - TAR archive operations
- `rich` - Beautiful terminal UI
- `typer` - CLI framework

**System Dependencies (minimal):**
- `par2cmdline` - PAR2 recovery files
- `b3sum` - BLAKE3 hashing

**Key Advantages:**
- **No external archive tools required** (7z, zstd, tar handled by Python)
- **Intelligent memory management** (auto-detects optimal settings)
- **Cross-platform compatibility** (Windows, macOS, Linux)
- **Smart parameter detection** (reads compression settings automatically)

### For Shell Scripts (legacy)

**Required Tools:**
- `7z` (7zip) - Archive extraction
- `tar` with POSIX/GNU format support
- `zstd` - Compression/decompression
- `sha256sum` - SHA-256 hashing
- `b3sum` - BLAKE3 hashing
- `par2` - PAR2 recovery files
- `bc` - Mathematical calculations

**Installation:**
```bash
# Ubuntu/Debian
sudo apt update && apt install tar zstd par2cmdline b3sum 7zip-full

# macOS (Homebrew)
brew install zstd par2 b3sum p7zip

# CentOS/RHEL/Rocky Linux
sudo yum install tar zstd par2cmdline b3sum p7zip
```

## File Organization

### Generated Files Structure

```
project-root/
├── coldstore/              # Python application source
├── archive-compress.sh     # Legacy shell scripts
├── verify-archive.sh
├── extract-archive.sh
├── verify-and-extract.sh
└── processed/              # Default output directory
    └── filename/           # Organized by subdirectories
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
- `.tar.zst.par2` - PAR2 main file (M3 feature)
- `.tar.zst.vol*.par2` - PAR2 recovery files (M3 feature)

## Development Notes

### Python Application Architecture
- **Modular design**: Separate core modules for compression, hashing, system checks
- **Rich logging**: Color-coded output with progress bars and tables
- **Intelligent automation**: Auto-detects compression parameters and memory requirements
- **Cross-platform**: Pure Python implementation with platform-specific optimizations
- **Memory optimization**: Automatic window_log selection based on file size
- **Error handling**: Comprehensive exception handling with detailed diagnostics

### Memory Management
- **Small files (<1MB)**: 1MB window (~1MB memory)
- **Medium files (1-10MB)**: 16MB window (~16MB memory)
- **Large files (10-100MB)**: 128MB window (~128MB memory)
- **Very large files (>100MB)**: 2GB window (~2GB memory)
- **Auto-detection**: Reads compression parameters from existing archives

### Shell Script Architecture (Legacy)
- Consistent color-coded logging
- Modular functions for reusability
- Comprehensive error handling
- Memory and disk space checking
- Support for flat and organized structures

## Troubleshooting

### Python Application Issues

1. **Memory errors**: Use `--no-long` or reduce compression level
2. **Missing dependencies**: Run `pip install -r requirements.txt`
3. **Permission errors**: Check file/directory permissions
4. **Archive corruption**: Use future PAR2 repair functionality

### Verification Workflow
**Always verify integrity before extraction:**
```bash
# Using coldstore (recommended)
coldstore -v verify archive.tar.zst

# Using legacy scripts
./verify-archive.sh -v archive.tar.zst
```

### Common Issues

1. **Extraction path problems**: Fixed in M2 - no more unwanted temp directories
2. **Memory optimization**: Automatic in coldstore, manual in shell scripts
3. **Cross-platform compatibility**: Handled by pure Python implementation
4. **Progress tracking**: Real-time progress bars and detailed statistics

If verification fails:
1. Check file corruption (PAR2 repair coming in M3)
2. Verify compression parameters auto-detection
3. Ensure sufficient disk space
4. Check Python library versions
