# Scripts 工具腳本

這個資料夾包含了用於批量處理歸檔檔案的工具腳本。

## 可用腳本

### pack_7z_batch.sh (Bash 版本)

**功能：** 批量處理指定資料夾中的所有7z檔案，對每個檔案執行 `coldstore pack` 命令並輸出到指定目錄。(適用於 Linux/macOS)

**使用方法：**
```bash
./scripts/pack_7z_batch.sh <輸入資料夾路徑> [輸出資料夾路徑]
```

**範例：**
```bash
# 處理當前目錄中的所有7z檔案，輸出到預設目錄 'processed'
./scripts/pack_7z_batch.sh .

# 處理指定目錄中的所有7z檔案，輸出到指定目錄
./scripts/pack_7z_batch.sh /path/to/archives /path/to/output

# 處理當前目錄的7z檔案，輸出到 ./output
./scripts/pack_7z_batch.sh . ./output

# 查看使用說明
./scripts/pack_7z_batch.sh --help
```

### pack_7z_batch.ps1 (PowerShell 版本)

**功能：** 批量處理指定資料夾中的所有7z檔案，對每個檔案執行 `coldstore pack` 命令並輸出到指定目錄。(適用於 Windows/跨平台 PowerShell)

**使用方法：**
```powershell
.\scripts\pack_7z_batch.ps1 <輸入資料夾路徑> [輸出資料夾路徑]
```

**範例：**
```powershell
# 處理當前目錄中的所有7z檔案，輸出到預設目錄 'processed'
.\scripts\pack_7z_batch.ps1 "."

# 處理指定目錄中的所有7z檔案，輸出到指定目錄
.\scripts\pack_7z_batch.ps1 "C:\Archives" "C:\Output"

# 處理當前目錄的7z檔案，輸出到 .\output
.\scripts\pack_7z_batch.ps1 "." ".\output"

# 查看內建說明文件
Get-Help .\scripts\pack_7z_batch.ps1 -Detailed
```

## 共同特色功能

**兩個版本都具備以下功能：**
- 自動搜尋輸入目錄中的所有7z檔案
- 支援指定輸出目錄，未指定時使用預設目錄 'processed'
- 自動創建輸出目錄（如果不存在）
- 彩色輸出顯示處理狀態
- 詳細的錯誤處理和進度報告
- 處理完成後顯示結果摘要
- 完整的說明文件和使用範例

## 必要條件

**兩個版本都需要：**
- 已安裝並配置 `coldstore` 命令

**Bash 版本額外需要：**
- 腳本有執行權限（使用 `chmod +x scripts/pack_7z_batch.sh` 設置）
- bash 3.2+ 支援（macOS 預設版本可用）

**PowerShell 版本額外需要：**
- PowerShell 5.0+ 或 PowerShell Core 6.0+
- 適當的執行策略設定（可能需要 `Set-ExecutionPolicy RemoteSigned`）

## 處理邏輯

**兩個版本採用相同的處理流程：**
1. 驗證輸入參數和輸入目錄存在性
2. 設定輸出目錄（使用者指定或預設 'processed'）
3. 創建輸出目錄（如果不存在）
4. 檢查 coldstore 命令是否可用
5. 掃描輸入目錄中的所有 .7z 檔案
6. 依序對每個檔案執行 `coldstore pack -o <輸出目錄>` 命令
7. 記錄成功和失敗的案例
8. 顯示最終處理結果摘要

## 平台選擇建議

- **Linux/macOS 環境：** 建議使用 `pack_7z_batch.sh` (Bash 版本)
- **Windows 環境：** 建議使用 `pack_7z_batch.ps1` (PowerShell 版本)
- **跨平台需求：** PowerShell Core 可在所有平台運行
