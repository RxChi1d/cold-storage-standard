#Requires -Version 5.0

<#
.SYNOPSIS
    批量處理7z檔案的PowerShell腳本

.DESCRIPTION
    對指定資料夾中的每個7z檔案執行coldstore pack命令並輸出到指定目錄

.PARAMETER InputPath
    包含7z檔案的目錄路徑

.PARAMETER OutputPath
    處理後檔案的輸出目錄 (可選，預設為 'processed')

.EXAMPLE
    .\pack_7z_batch.ps1 "C:\Archives"
    處理指定目錄中的所有7z檔案，輸出到預設目錄 'processed'

.EXAMPLE
    .\pack_7z_batch.ps1 "C:\Archives" "C:\Output"
    處理指定目錄中的所有7z檔案，輸出到指定目錄

.EXAMPLE
    .\pack_7z_batch.ps1 "." ".\output"
    處理當前目錄的7z檔案，輸出到 .\output
#>

param(
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "包含7z檔案的目錄路徑")]
    [string]$InputPath,

    [Parameter(Mandatory = $false, Position = 1, HelpMessage = "處理後檔案的輸出目錄")]
    [string]$OutputPath = "processed"
)

# 設定錯誤處理
$ErrorActionPreference = "Stop"

# 輔助函數
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
    Write-Host "使用方法: .\pack_7z_batch.ps1 <輸入資料夾路徑> [輸出資料夾路徑]" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "功能："
    Write-Host "  對指定資料夾中的每個7z檔案執行 'coldstore pack' 命令"
    Write-Host ""
    Write-Host "參數："
    Write-Host "  <輸入資料夾路徑>    包含7z檔案的目錄路徑"
    Write-Host "  [輸出資料夾路徑]    處理後檔案的輸出目錄 (可選，預設為 'processed')"
    Write-Host ""
    Write-Host "範例："
    Write-Host "  .\pack_7z_batch.ps1 'C:\Archives'                    # 輸出到預設目錄 'processed'"
    Write-Host "  .\pack_7z_batch.ps1 'C:\Archives' 'C:\Output'        # 輸出到指定目錄"
    Write-Host "  .\pack_7z_batch.ps1 '.' '.\output'                   # 當前目錄的7z檔案輸出到 .\output"
    Write-Host ""
}

# 主程式邏輯
try {
    # 檢查輸入目錄是否存在
    if (-not (Test-Path -Path $InputPath -PathType Container)) {
        Write-LogError "輸入目錄不存在: $InputPath"
        Show-Usage
        exit 1
    }

    # 轉換為絕對路徑
    $InputPath = (Resolve-Path -Path $InputPath).Path
    Write-LogInfo "輸入目錄: $InputPath"

    # 創建輸出目錄（如果不存在）
    if (-not (Test-Path -Path $OutputPath -PathType Container)) {
        Write-LogInfo "創建輸出目錄: $OutputPath"
        try {
            New-Item -Path $OutputPath -ItemType Directory -Force | Out-Null
        }
        catch {
            Write-LogError "無法創建輸出目錄: $OutputPath"
            Write-LogError $_.Exception.Message
            exit 1
        }
    }

    # 轉換輸出目錄為絕對路徑
    $OutputPath = (Resolve-Path -Path $OutputPath).Path
    Write-LogInfo "輸出目錄: $OutputPath"

    # 檢查coldstore命令是否可用
    try {
        $null = Get-Command "coldstore" -ErrorAction Stop
    }
    catch {
        Write-LogError "找不到 coldstore 命令。請確保已安裝並在PATH中"
        exit 1
    }

    # 切換到輸入目錄
    Push-Location -Path $InputPath

    try {
        # 找出所有7z檔案
        $sevenZipFiles = Get-ChildItem -Path "." -Filter "*.7z" -File | Sort-Object Name

        if ($sevenZipFiles.Count -eq 0) {
            Write-LogWarning "在目錄 $InputPath 中沒有找到任何7z檔案"
            exit 0
        }

        Write-LogInfo "找到 $($sevenZipFiles.Count) 個7z檔案"

        # 處理每個7z檔案
        $successCount = 0
        $errorCount = 0

        foreach ($file in $sevenZipFiles) {
            Write-LogInfo "正在處理: $($file.Name) -> $OutputPath"

            try {
                # 執行coldstore pack命令
                $process = Start-Process -FilePath "coldstore" -ArgumentList "pack", "-o", $OutputPath, $file.Name -Wait -PassThru -NoNewWindow

                if ($process.ExitCode -eq 0) {
                    Write-LogSuccess "成功處理: $($file.Name)"
                    $successCount++
                }
                else {
                    Write-LogError "處理失敗: $($file.Name) (退出代碼: $($process.ExitCode))"
                    $errorCount++
                }
            }
            catch {
                Write-LogError "處理失敗: $($file.Name)"
                Write-LogError $_.Exception.Message
                $errorCount++
            }

            Write-Host ""  # 空行分隔
        }

        # 顯示結果摘要
        Write-Host "======== 處理結果摘要 ========" -ForegroundColor Cyan
        Write-LogInfo "總檔案數: $($sevenZipFiles.Count)"
        Write-LogSuccess "成功: $successCount"
        if ($errorCount -gt 0) {
            Write-LogError "失敗: $errorCount"
        }

        if ($errorCount -eq 0) {
            Write-LogSuccess "所有檔案處理完成！"
            exit 0
        }
        else {
            Write-LogWarning "部分檔案處理失敗，請檢查錯誤訊息"
            exit 1
        }
    }
    finally {
        # 恢復原始目錄
        Pop-Location
    }
}
catch {
    Write-LogError "腳本執行失敗: $($_.Exception.Message)"
    exit 1
}
