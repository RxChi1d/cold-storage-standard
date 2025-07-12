# Cold Storage Standard - Development Log

## Project Overview
冷儲存標準是一個高性能的數據歸檔和保護工具，專為研究數據的長期保存而設計。

## Current Implementation Status

### Phase 1: Multi-Format Archive Support ✅
**Status**: Complete
- 支援10+種壓縮格式（7z, ZIP, RAR, TAR系列等）
- 智能格式檢測和處理
- 統一的歸檔處理接口
- 跨平台system tool檢查

### Phase 2: PAR2 Recovery System ✅
**Status**: Complete - **Enhanced with par2cmdline-turbo**

#### 舊實現問題：
- 依賴系統安裝的par2工具
- 跨平台部署困難
- 性能較慢

#### 新實現優勢：
- **自動下載par2cmdline-turbo**：無需手動安裝
- **極高性能**：處理速度比原始par2快6-8倍
- **完全獨立**：不依賴系統par2工具
- **跨平台支援**：macOS (x64/ARM64), Linux (x64/ARM64), Windows (x64)

#### 性能對比（25GB數據測試）：
- 原始par2: 8分55秒
- parpar: 3分10秒
- **par2cmdline-turbo: 1分14秒** ⚡️

## 新PAR2實現特性

### 自動工具管理
```python
from coldstore.core.par2 import PAR2Engine

# 自動下載和配置par2cmdline-turbo
engine = PAR2Engine(recovery_percent=10)

# 生成PAR2文件
par2_files = engine.generate_par2("archive.tar.zst")

# 驗證文件完整性
result = engine.verify_par2("archive.tar.zst.par2")

# 修復損壞的文件
repair_result = engine.repair_files("archive.tar.zst.par2")
```

### 平台支援
- **macOS**: Intel x64, Apple Silicon ARM64
- **Linux**: x86_64, ARM64
- **Windows**: x86_64

### 安裝位置
- 工具自動下載到 `~/.coldstore/tools/`
- 避免需要系統管理員權限
- 支援離線使用

## 使用方法

### 1. 打包歸檔（自動PAR2）
```bash
# 使用預設10%恢復率
coldstore pack input_archive.rar --output-dir processed/

# 自訂恢復率（5%，適合小檔案）
coldstore pack input_archive.rar -r 5 --output-dir processed/

# 高安全性恢復率（25%，適合重要檔案）
coldstore pack input_archive.rar --recovery-percent 25 --output-dir processed/
```
- 自動解壓縮並重新打包為tar.zst
- 生成SHA-256, BLAKE3雜湊
- 可調整PAR2恢復數據比例（1-100%，預設10%）

### 2. 驗證完整性
```bash
coldstore verify processed/archive.tar.zst
```
- 驗證歸檔完整性
- 檢查PAR2恢復數據

### 3. 修復損壞文件
```bash
coldstore repair processed/archive.tar.zst.par2
```
- 使用PAR2恢復損壞文件
- 自動驗證修復結果

## 技術亮點

### 1. 智能工具管理
- 自動檢測現有par2cmdline-turbo安裝
- 自動下載適合平台的二進制文件
- 版本管理和更新

### 2. 高效能處理
- 使用ParPar的高性能後端
- 多線程並行處理
- SIMD指令優化（SSE2, AVX2, AVX512等）

### 3. 錯誤處理
- 詳細的錯誤診斷
- 自動重試機制
- 用戶友好的錯誤訊息

## 系統要求

### 最低要求
- Python 3.8+
- 網路連接（首次下載工具）
- 磁碟空間：~50MB（工具檔案）

### 推薦配置
- 多核心CPU（PAR2處理可充分利用）
- 8GB+ RAM（處理大型歸檔）
- SSD儲存（提升I/O性能）

## 故障排除

### 1. 工具下載失敗
如果自動下載失敗，可手動下載：
```bash
# 從官方releases頁面下載
wget https://github.com/animetosho/par2cmdline-turbo/releases/download/v1.3.0/par2cmdline-turbo-v1.3.0-macos-arm64.tar.xz

# 解壓縮到工具目錄
mkdir -p ~/.coldstore/tools
tar -xf par2cmdline-turbo-v1.3.0-macos-arm64.tar.xz -C ~/.coldstore/tools
```

### 2. 權限問題
確保工具目錄有寫入權限：
```bash
chmod +x ~/.coldstore/tools/par2
```

### 3. 網路問題
- 檢查網路連接
- 檢查防火牆設定
- 考慮使用代理服務器

## 開發指南

### 擴展PAR2功能
```python
# 自訂恢復百分比
engine = PAR2Engine(recovery_percent=15)

# 獲取版本信息
version = engine.get_version()

# 檢查工具狀態
if engine.par2_path:
    print(f"Using PAR2 tool: {engine.par2_path}")
```

### 添加新平台支援
在`PAR2Engine.TURBO_RELEASES`中添加新的平台配置：
```python
"Linux": {
    "riscv64": {
        "url": "https://github.com/animetosho/par2cmdline-turbo/releases/download/v1.3.0/par2cmdline-turbo-v1.3.0-linux-riscv64.tar.xz",
        "hash": "sha256:actual_hash_here"
    }
}
```

## 未來發展

### 即將推出的功能
1. **進度報告**：實時顯示PAR2處理進度
2. **批量處理**：支援目錄批量PAR2生成
3. **雲端整合**：支援雲端儲存的PAR2驗證
4. **智能參數調優**：根據檔案大小自動建議最佳恢復率

### 性能優化
1. **GPU加速**：利用OpenCL進行GPU運算
2. **記憶體優化**：大檔案的串流處理
3. **並行I/O**：非同步檔案讀寫

## 版本歷史

### v2.1.0 (當前版本)
- ✅ **PAR2參數化控制**：pack命令新增 `--recovery-percent` 參數
- ✅ **簡化驗證修復**：verify和repair命令自動工作，無需額外參數
- ✅ **修復PAR2命名**：修正PAR2檔案命名邏輯，確保verify/repair正確識別
- ✅ **提升用戶體驗**：恢復率可調整（1-100%），預設10%

### v2.0.0
- ✅ 整合par2cmdline-turbo
- ✅ 自動工具下載
- ✅ 跨平台支援
- ✅ 高性能PAR2處理

### v1.0.0 (舊版本)
- ✅ 多格式歸檔支援
- ✅ 基本PAR2功能
- ⚠️ 依賴系統par2工具

## 致謝
- **par2cmdline-turbo**: 提供高性能PAR2實現
- **ParPar**: 高性能PAR2後端引擎
- **coldstore team**: 專案開發和維護

## 授權
本專案使用MIT授權，par2cmdline-turbo使用GPL v2授權。

## 聯絡方式
- 問題回報：GitHub Issues
- 功能建議：GitHub Discussions
- 技術交流：專案Wiki

---

*最後更新：2025-07-13*
