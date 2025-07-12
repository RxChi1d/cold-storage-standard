#!/bin/bash

# Batch processing script for 7z files
# Function: Execute coldstore pack command for each 7z file in specified directory

set -e  # Exit immediately on error

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_detail() {
    echo -e "${NC}[DETAIL]${NC} $1"
}

# Show usage instructions
show_usage() {
    echo "Usage: $0 <input_directory> [output_directory]"
    echo
    echo "Function:"
    echo "  Execute 'coldstore pack' command for each 7z file in specified directory"
    echo
    echo "Parameters:"
    echo "  <input_directory>     Directory path containing 7z files"
    echo "  [output_directory]    Output directory for processed files (optional, defaults to 'processed')"
    echo
    echo "Examples:"
    echo "  $0 /path/to/archives                          # Output to default 'processed' directory"
    echo "  $0 /path/to/archives /path/to/output          # Output to specified directory"
    echo "  $0 . ./output                                 # Process current directory 7z files to ./output"
}

# Check parameters
if [ $# -eq 0 ]; then
    log_error "Missing input directory parameter"
    echo
    show_usage
    exit 1
fi

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage
    exit 0
fi

INPUT_DIR="$1"
OUTPUT_DIR="${2:-processed}"  # Use default value "processed" if second parameter not provided

# Check if input directory exists
if [ ! -d "$INPUT_DIR" ]; then
    log_error "Input directory does not exist: $INPUT_DIR"
    exit 1
fi

# Convert to absolute path
INPUT_DIR=$(cd "$INPUT_DIR" && pwd)
log_info "Input directory: $INPUT_DIR"

# Create output directory if it doesn't exist
if [ ! -d "$OUTPUT_DIR" ]; then
    log_info "Creating output directory: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR" || {
        log_error "Unable to create output directory: $OUTPUT_DIR"
        exit 1
    }
fi

# Convert output directory to absolute path
OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd)
log_info "Output directory: $OUTPUT_DIR"

# Check if coldstore command is available
if ! command -v coldstore &> /dev/null; then
    log_error "coldstore command not found. Please ensure it's installed and in PATH"
    exit 1
fi

# Change to input directory
cd "$INPUT_DIR"

# Find all 7z files and count them
seven_zip_count=0
temp_file=$(mktemp)
# Simple cleanup: ensure temp file is cleaned up when script exits
trap 'rm -f "$temp_file"' EXIT

find . -maxdepth 1 -name "*.7z" -type f | sort > "$temp_file"

# Count files
while IFS= read -r line; do
    seven_zip_count=$((seven_zip_count + 1))
done < "$temp_file"

if [ $seven_zip_count -eq 0 ]; then
    log_warning "No 7z files found in directory $INPUT_DIR"
    exit 0
fi

log_info "Found $seven_zip_count 7z files"

# Process each 7z file
success_count=0
error_count=0

while IFS= read -r file; do
    # Remove ./ prefix
    clean_filename="${file#./}"

    log_info "Processing: $clean_filename -> $OUTPUT_DIR"

    if coldstore pack -o "$OUTPUT_DIR" "$clean_filename"; then
        log_success "Successfully processed: $clean_filename"
        success_count=$((success_count + 1))
    else
        log_error "Failed to process: $clean_filename"
        error_count=$((error_count + 1))
    fi

    echo  # Empty line separator
done < "$temp_file"

# Display result summary
echo "======== Processing Summary ========"
log_info "Total files: $seven_zip_count"
log_success "Successful: $success_count"
if [ $error_count -gt 0 ]; then
    log_error "Failed: $error_count"
fi

if [ $error_count -eq 0 ]; then
    log_success "All files processed successfully!"
    exit 0
else
    log_warning "Some files failed to process, please check error messages"
    exit 1
fi
