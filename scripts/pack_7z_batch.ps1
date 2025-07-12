#Requires -Version 5.0

<#
.SYNOPSIS
    Batch processing script for 7z files

.DESCRIPTION
    Execute coldstore pack command for each 7z file in specified directory and output to target directory

.PARAMETER InputPath
    Directory path containing 7z files

.PARAMETER OutputPath
    Output directory for processed files (optional, defaults to 'processed')

.EXAMPLE
    .\pack_7z_batch.ps1 "C:\Archives"
    Process all 7z files in specified directory, output to default 'processed' directory

.EXAMPLE
    .\pack_7z_batch.ps1 "C:\Archives" "C:\Output"
    Process all 7z files in specified directory, output to specified directory

.EXAMPLE
    .\pack_7z_batch.ps1 "." ".\output"
    Process 7z files in current directory, output to .\output
#>

param(
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "Directory path containing 7z files")]
    [string]$InputPath,

    [Parameter(Mandatory = $false, Position = 1, HelpMessage = "Output directory for processed files")]
    [string]$OutputPath = "processed"
)

# Set error handling
$ErrorActionPreference = "Stop"

# Helper functions
function Write-LogInfo {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-LogSuccess {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Write-LogWarning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-LogError {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-LogDetail {
    param([string]$Message)
    Write-Host "[DETAIL] $Message" -ForegroundColor Gray
}

function Show-Usage {
    Write-Host ""
    Write-Host "Usage: .\pack_7z_batch.ps1 <input_directory> [output_directory]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Function:"
    Write-Host "  Execute 'coldstore pack' command for each 7z file in specified directory"
    Write-Host ""
    Write-Host "Parameters:"
    Write-Host "  <input_directory>     Directory path containing 7z files"
    Write-Host "  [output_directory]    Output directory for processed files (optional, defaults to 'processed')"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\pack_7z_batch.ps1 'C:\Archives'                    # Output to default 'processed' directory"
    Write-Host "  .\pack_7z_batch.ps1 'C:\Archives' 'C:\Output'        # Output to specified directory"
    Write-Host "  .\pack_7z_batch.ps1 '.' '.\output'                   # Process current directory 7z files to .\output"
    Write-Host ""
}

# Main program logic
try {
    # Check if input directory exists
    if (-not (Test-Path -Path $InputPath -PathType Container)) {
        Write-LogError "Input directory does not exist: $InputPath"
        Show-Usage
        exit 1
    }

    # Convert to absolute path
    $InputPath = (Resolve-Path -Path $InputPath).Path
    Write-LogInfo "Input directory: $InputPath"

    # Create output directory if it doesn't exist
    if (-not (Test-Path -Path $OutputPath -PathType Container)) {
        Write-LogInfo "Creating output directory: $OutputPath"
        try {
            New-Item -Path $OutputPath -ItemType Directory -Force | Out-Null
        }
        catch {
            Write-LogError "Unable to create output directory: $OutputPath"
            Write-LogError $_.Exception.Message
            exit 1
        }
    }

    # Convert output directory to absolute path
    $OutputPath = (Resolve-Path -Path $OutputPath).Path
    Write-LogInfo "Output directory: $OutputPath"

    # Check if coldstore command is available
    try {
        $null = Get-Command "coldstore" -ErrorAction Stop
    }
    catch {
        Write-LogError "coldstore command not found. Please ensure it's installed and in PATH"
        exit 1
    }

    # Change to input directory
    Push-Location -Path $InputPath

    try {
        # Find all 7z files
        $sevenZipFiles = Get-ChildItem -Path "." -Filter "*.7z" -File | Sort-Object Name

        if ($sevenZipFiles.Count -eq 0) {
            Write-LogWarning "No 7z files found in directory $InputPath"
            exit 0
        }

        Write-LogInfo "Found $($sevenZipFiles.Count) 7z files"

        # Process each 7z file
        $successCount = 0
        $errorCount = 0

        foreach ($file in $sevenZipFiles) {
            Write-LogInfo "Processing: $($file.Name) -> $OutputPath"

            try {
                # Execute coldstore pack command
                $process = Start-Process -FilePath "coldstore" -ArgumentList "pack", "-o", $OutputPath, $file.Name -Wait -PassThru -NoNewWindow

                if ($process.ExitCode -eq 0) {
                    Write-LogSuccess "Successfully processed: $($file.Name)"
                    $successCount++
                }
                else {
                    Write-LogError "Failed to process: $($file.Name) (exit code: $($process.ExitCode))"
                    $errorCount++
                }
            }
            catch {
                Write-LogError "Failed to process: $($file.Name)"
                Write-LogError $_.Exception.Message
                $errorCount++
            }

            Write-Host ""  # Empty line separator
        }

        # Display result summary
        Write-Host "======== Processing Summary ========" -ForegroundColor Cyan
        Write-LogInfo "Total files: $($sevenZipFiles.Count)"
        Write-LogSuccess "Successful: $successCount"
        if ($errorCount -gt 0) {
            Write-LogError "Failed: $errorCount"
        }

        if ($errorCount -eq 0) {
            Write-LogSuccess "All files processed successfully!"
            exit 0
        }
        else {
            Write-LogWarning "Some files failed to process, please check error messages"
            exit 1
        }
    }
    finally {
        # Restore original directory
        Pop-Location
    }
}
catch {
    Write-LogError "Script execution failed: $($_.Exception.Message)"
    exit 1
}
