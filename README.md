# 冷儲存封存工具集 (Cold Storage Archive Toolkit)

一套專為長期冷儲存設計的檔案封存工具，提供從壓縮、驗證到解壓縮的完整解決方案。

![Version](https://img.shields.io/badge/version-v2.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Shell](https://img.shields.io/badge/shell-bash-yellow)

## 🎯 專案目標

建立一套專業的冷儲存封存系統，確保資料能夠在 10 年後依然完整可讀，具備：

- **長期保存性**: 使用標準格式（tar + zstd），確保未來相容性
- **完整性保證**: 多重驗證機制（SHA-256 + BLAKE3 + PAR2）
- **錯誤修復**: 10% PAR2 冗餘，可修復檔案損壞
- **高壓縮比**: zstd 最佳化，壓縮比可達 60-80%
- **可重現性**: deterministic tar，確保相同輸入產生相同輸出

## 📁 工具概覽

| 腳本 | 版本 | 功能 | 使用場景 |
|------|------|------|----------|
| `archive-compress.sh` | v2.1 | 7z → tar.zst 轉換 + 完整封存 | 建立冷儲存檔案 |
| `verify-archive.sh` | v1.0 | 完整性驗證 | 定期檢查檔案健康狀態 |
| `extract-archive.sh` | v2.0 | tar.zst 解壓縮 | 快速解壓縮（已驗證檔案） |
| `verify-and-extract.sh` | v1.0 | 驗證 + 解壓縮組合流程 | 安全的完整處理流程 |

## 🔧 系統需求

### 必要工具
```bash
# Ubuntu/Debian
sudo apt update && apt install tar zstd par2cmdline b3sum 7zip-full

# macOS (使用 Homebrew)
brew install zstd par2 b3sum p7zip

# CentOS/RHEL/Rocky Linux
sudo yum install tar zstd par2cmdline b3sum p7zip
```

### 系統規格建議
- **記憶體**: 4GB+ RAM（`--long=31` 需要約 2.2GB）
- **磁碟空間**: 原始檔案大小的 2-3 倍（含臨時檔案和冗餘）
- **處理器**: 多核心 CPU（zstd 支援多執行緒）
- **儲存**: 建議使用 SSD 提升處理效能

## 🚀 快速開始

### 1. 壓縮檔案（建立冷儲存檔案）
```bash
# 基本使用：處理當前目錄的 7z 檔案
./archive-compress.sh

# 處理指定目錄
./archive-compress.sh /path/to/7z/files

# 自訂參數
./archive-compress.sh -l 15 -t 4 -o ~/backup /path/to/files
```

### 2. 驗證檔案完整性
```bash
# 驗證單一檔案
./verify-archive.sh archive.tar.zst

# 驗證多個檔案
./verify-archive.sh *.tar.zst

# 驗證整個目錄
./verify-archive.sh -d ./processed
```

### 3. 解壓縮檔案
```bash
# 完整流程（推薦）：先驗證再解壓縮
./verify-and-extract.sh archive.tar.zst

# 快速解壓縮（已確認檔案完整性）
./extract-archive.sh archive.tar.zst

# 解壓縮到指定目錄
./extract-archive.sh -o /tmp/extract archive.tar.zst
```

## 📊 輸出檔案格式

每個 7z 檔案經處理後會產生以下檔案：

```
processed/
└── archive_name/                          # 子目錄組織（預設）
    ├── archive_name.tar.zst              # 主檔（zstd 壓縮的 tar）
    ├── archive_name.tar.zst.sha256       # SHA-256 雜湊
    ├── archive_name.tar.zst.blake3       # BLAKE3 雜湊
    ├── archive_name.tar.zst.par2         # PAR2 主檔案
    └── archive_name.tar.zst.vol000+xxx.par2  # PAR2 修復檔案（10% 冗餘）
```

## 🛠️ 詳細使用說明

### archive-compress.sh - 壓縮工具

將 7z 檔案轉換為符合冷儲存標準的 tar.zst 格式。

#### 主要特性
- **分離式處理**: tar 創建 → 驗證 → zstd 壓縮（符合冷儲存 SOP）
- **deterministic tar**: 使用 `--sort=name` 確保可重現性
- **高效壓縮**: zstd 最佳化參數（`--long=31`，2GB dictionary window）
- **多重驗證**: 5 階段驗證流程
- **智能組織**: 子目錄結構避免檔案混亂

#### 常用參數
```bash
./archive-compress.sh [選項] [工作目錄]

# 主要選項
-l, --level NUM        壓縮等級 (1-22, 預設: 19)
-t, --threads NUM      執行緒數 (0=所有核心, 預設: 0)
-o, --output-dir DIR   輸出目錄 (預設: ./processed)
--flat                 扁平結構，不創建子目錄
--no-long              停用長距離匹配
--no-check             停用完整性檢查
```

#### 使用範例
```bash
# 標準使用
./archive-compress.sh ~/archives

# 高壓縮比 + 自訂輸出
./archive-compress.sh -l 22 -o /backup ~/archives

# 快速處理（降低壓縮等級）
./archive-compress.sh -l 12 -t 8 ~/archives

# 向後相容（扁平結構）
./archive-compress.sh --flat ~/archives
```

### verify-archive.sh - 驗證工具

對 tar.zst 檔案進行全面完整性檢查。

#### 驗證項目
- ✅ zstd 檔案完整性檢查
- ✅ SHA-256 雜湊驗證
- ✅ BLAKE3 雜湊驗證  
- ✅ PAR2 冗餘完整性檢查
- ✅ tar 內容結構驗證

#### 常用參數
```bash
./verify-archive.sh [選項] [檔案路徑...]

# 主要選項
-d, --directory DIR    驗證目錄中的所有 tar.zst 檔案
-v, --verbose         顯示詳細驗證資訊
-q, --quiet           安靜模式，只顯示結果
```

#### 使用範例
```bash
# 驗證單一檔案
./verify-archive.sh archive.tar.zst

# 批量驗證
./verify-archive.sh *.tar.zst

# 驗證目錄（詳細模式）
./verify-archive.sh -v -d ./processed

# 定期檢查（安靜模式）
./verify-archive.sh -q -d /backup/archives
```

### extract-archive.sh - 解壓縮工具

專門負責 tar.zst 檔案的解壓縮操作。

#### 主要特性
- **兩階段解壓縮**: zstd 解壓縮 → tar 展開
- **安全目標目錄**: 自動創建目錄，覆蓋保護
- **效能最佳化**: 使用正確的 zstd 參數
- **基本驗證**: 解壓縮後檔案數量和大小統計

#### 常用參數
```bash
./extract-archive.sh [選項] <檔案路徑>

# 主要選項
-o, --output DIR      指定解壓縮輸出目錄
-f, --force          強制覆蓋現有檔案
-v, --verbose        顯示詳細解壓縮資訊
-q, --quiet          安靜模式
```

#### 使用範例
```bash
# 基本解壓縮（解壓縮到檔案名目錄）
./extract-archive.sh archive.tar.zst

# 指定輸出目錄
./extract-archive.sh -o /tmp/extract archive.tar.zst

# 強制覆蓋 + 詳細模式
./extract-archive.sh -f -v archive.tar.zst
```

### verify-and-extract.sh - 組合工具

提供完整的驗證與解壓縮流程。

#### 工作流程
1. **第一階段**: 使用 `verify-archive.sh` 進行完整驗證
2. **第二階段**: 使用 `extract-archive.sh` 進行安全解壓縮

#### 常用參數
```bash
./verify-and-extract.sh [選項] <檔案路徑>

# 主要選項
-o, --output DIR      指定解壓縮輸出目錄
-f, --force          強制覆蓋現有檔案
-v, --verbose        顯示詳細資訊
--verify-only        僅執行驗證，不解壓縮
--skip-verify        跳過驗證直接解壓縮（不建議）
```

#### 使用範例
```bash
# 完整流程（推薦）
./verify-and-extract.sh archive.tar.zst

# 僅驗證模式
./verify-and-extract.sh --verify-only archive.tar.zst

# 指定輸出目錄
./verify-and-extract.sh -o /tmp/restore archive.tar.zst

# 詳細模式
./verify-and-extract.sh -v archive.tar.zst
```

## 🔄 典型工作流程

### 冷儲存建立流程
```bash
# 1. 壓縮建立冷儲存檔案
./archive-compress.sh ~/important_data

# 2. 驗證生成的檔案
./verify-archive.sh -d ./processed

# 3. 移動到冷儲存位置
cp -r ./processed/* /backup/cold_storage/
```

### 冷儲存恢復流程
```bash
# 1. 定期驗證（建議每季度）
./verify-archive.sh -d /backup/cold_storage

# 2. 需要時恢復檔案
./verify-and-extract.sh /backup/cold_storage/archive.tar.zst

# 3. 僅驗證不解壓縮
./verify-and-extract.sh --verify-only /backup/cold_storage/archive.tar.zst
```

## 🔒 安全特性

### 完整性保證
- **多重校驗**: SHA-256 + BLAKE3 雙重雜湊
- **錯誤修復**: PAR2 10% 冗餘，可修復檔案損壞
- **分階段驗證**: 每個處理步驟都有驗證機制

### 可重現性
- **deterministic tar**: 相同輸入保證相同輸出
- **標準格式**: 使用 POSIX tar 格式，確保跨平台相容

### 長期保存
- **標準工具**: 基於 tar、zstd 等廣泛支援的格式
- **向前相容**: 10 年後依然可用標準工具讀取

## 📈 效能特性

### 壓縮效能
- **高壓縮比**: 通常可達 60-80% 壓縮比
- **多執行緒**: 充分利用多核 CPU
- **記憶體最佳化**: 2GB dictionary window 提升大檔案壓縮率

### 驗證效能
- **並行處理**: 支援批量驗證
- **增量檢查**: 可選擇性驗證特定項目
- **快速模式**: 安靜模式適合自動化腳本

## 🚨 注意事項

### 資源需求
- 處理大檔案（>2GB）時需要較長時間
- `--long=31` 參數需要約 2.2GB RAM
- 建議在 SSD 上進行處理以提升效能

### 磁碟空間
- 處理過程中會產生臨時檔案
- 需要至少原始檔案大小 2-3 倍的可用空間
- PAR2 冗餘額外占用 10% 空間

### 相容性
- 所有腳本需要在同一目錄或 PATH 中
- 需要 bash 4.0+ 版本
- 推薦在 Linux/macOS 環境使用

## 📋 疑難排解

### 常見問題

**Q: 出現 "command not found" 錯誤**
```bash
# 檢查必要工具是否安裝
which zstd tar par2 b3sum

# Ubuntu/Debian 安裝
sudo apt install tar zstd par2cmdline b3sum
```

**Q: 記憶體不足錯誤**
```bash
# 使用較小的 dictionary window
./archive-compress.sh --no-long

# 或降低壓縮等級
./archive-compress.sh -l 12
```

**Q: PAR2 驗證失敗**
```bash
# 嘗試修復
par2 repair archive.tar.zst.par2

# 檢查檔案是否確實損壞
./verify-archive.sh -v archive.tar.zst
```

**Q: 權限錯誤**
```bash
# 確保腳本有執行權限
chmod +x *.sh

# 檢查目錄寫入權限
ls -la
```

## 🤝 最佳實踐

### 定期維護
- 每季度執行完整性驗證
- 定期測試恢復流程
- 保留多份備份在不同位置

### 效能最佳化
- 在 SSD 上進行處理
- 根據硬體調整執行緒數量
- 大批量處理時使用安靜模式

### 安全建議
- 使用完整流程（verify-and-extract.sh）
- 保留原始檔案直到驗證完成
- 定期更新工具版本

## 📄 授權協議

MIT License - 詳見 LICENSE 檔案

---

*本工具集專為長期冷儲存設計，確保您的重要資料能夠安全保存並在未來完整恢復。* 