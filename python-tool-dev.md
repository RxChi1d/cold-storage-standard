# Python CLI 版 Cold Storage Standard 工作交接文件

## 0. 概要

* **目的**：將現有 Bash 原型（`archive-compress.sh`）重構為跨平台 Python CLI。
* **核心要求**：

  1. 使用 **uv** 作為套件管理器（`uv venv` + `uv add`/`uv pip install`）。
  2. 禁止直接在 `main` 分支開發；採用功能分支＋PR 工作流。
  3. 保持輸出格式：`tar.zst` + `*.sha256` + `*.blake3` + `*.par2`。
  4. 對外交付單檔可執行檔（PyInstaller one‑file）。

---

## 1. Git 分支策略

| 分支          | 用途             | 保護規則                    |
| ----------- | -------------- | ----------------------- |
| `main`      | 穩定釋出；只合併 tag 版 | 必須 PR + Squash + CI 全通過 |
| `develop`   | 日常整合           | 允許快速合併，多人協作             |
| `feat/<功能>` | 單一功能/修補        | 完成交付 PR -> `develop`    |

> **第一支分支**：`feat/python-cli-baseline`。

---

## 2. 開發環境

```bash
# 建立隔離環境
uv venv .venv

# 目前尚無相依套件
# 後續開發過程請使用 uv add 逐一加入，例如：
#   uv add typer rich loguru            # CLI 框架 + 美化輸出 + 日誌
#   uv add python-zstandard              # 壓縮
#   uv add blake3                        # BLAKE3 雜湊
#   uv add par2cmdline-turbo             # 冗餘

# 工具型套件安裝
uv tool install ruff           # 格式化與靜態檢查
```

* 建議 **Python 版本：>=3.12**（內建 `compression.zstd`，效能與相容性最佳）。
* 格式化與靜態檢查統一使用 **ruff**（`ruff format` / `ruff check`），並透過 pre-commit 鉤子自動執行。

## 3. 相依套件規劃

目前尚未鎖定任何第三方相依；請在開發過程中視功能需求以 `uv add <package>` 加入。

| 類別  | 套件                                   | 目的                                    | 優先級 |
| --- | ------------------------------------ | ------------------------------------- | --- |
| CLI | `typer`                              | 型別安全 CLI 框架，支援子命令                    | 必要  |
| 壓縮  | `python-zstandard` (推薦) / `pyzstd` (選配) | `python-zstandard` API 完整、跨平台穩定；`pyzstd` 速度更高 | 必要  |
| 校驗  | `blake3`, `hashlib`(內建 SHA‑256)      | 產生雙雜湊檔                                | 必要  |
| 冗餘  | `par2cmdline-turbo`                   | wheel 內含各平台 binary；subprocess 呼叫      | 必要  |
| 日誌  | `loguru` + `rich.console`            | **彩色分級日誌** + 結構化輸出，參考 bash 腳本的日誌系統   | 必要  |
| 進度  | `rich.progress`                      | **Fancy 進度條**，替代 bash 腳本的 progress_bar | 必要  |
| 系統  | `platformdirs`, `psutil`             | 跨平台路徑、**系統資源檢查**（記憶體、磁碟空間）          | 推薦  |
| 格式  | `rich.table`, `rich.panel`          | **美化統計顯示**，替代 bash 腳本的報告系統          | 推薦  |
| 工具  | `humanize`                           | 檔案大小格式化（1.2GB vs 1234567890 bytes）   | 推薦  |

> **重要**：以 `rich` 為核心的 UX 體系，整合日誌、進度、統計報告。

---

## 4. 任務里程碑

| 里程碑                   | 內容                                                                                                                                                  | 估時 |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -- |
| **M0 環境&骨架**          | ‑ 建立 `pyproject.toml` (PEP 621) <br>‑ 初始化 Typer CLI (`coldstore pack/verify/repair`) <br>‑ 加入 CI、pre‑commit <br>‑ **Rich 日誌系統** (替代 bash 彩色日誌) | 3d |
| **M1 核心功能轉移**         | ‑ **分離模式** 實現 (tar → zstd，非串流)<br>‑ **智能 7z 結構檢測**<br>‑ **檔案組織系統** (子目錄 vs 扁平)<br>‑ 完成 **壓縮 + SHA256 + BLAKE3**                          | 5d |
| **M2 冗餘&驗證**          | ‑ 整合 `par2cmdline-turbo` <br>‑ **5層驗證機制** (zstd + tar + 雙雜湊 + PAR2)<br>‑ 支援 `--redundancy 10%` 參數                                              | 4d |
| **M3 子命令完整化**         | ‑ `coldstore verify` 與 `coldstore repair` 子命令<br>‑ **統一錯誤處理&診斷資訊**                                                                              | 3d |
| **M4 UX & 系統整合**      | ‑ **Rich 進度條** + 統計報告<br>‑ **系統資源檢查** (記憶體、磁碟)<br>‑ **參數支援** (`-o`, `--flat`, `--no-long`)<br>‑ 友善錯誤訊息                                     | 3d |
| **M5 打包 & 發佈**        | ‑ `uv pip install pyinstaller` <br>‑ `pyinstaller --onefile --name coldstore` <br>‑ Draft GitHub Release                                            | 2d |
| **M6 文件**             | ‑ README、使用手冊、快速上手                                                                                                                                  | 2d |

> ⚠️ 以上為理想工時；實際依開發複雜度調整。

---

## 5. 技術實現細節

### 5.1 日誌系統設計

參考 bash 腳本的彩色日誌系統，使用 `loguru` + `rich.console`：

```python
# 日誌等級對應 bash 函數
log_info()     -> logger.info()     # 藍綠色
log_success()  -> logger.success()  # 綠色 +
log_warning()  -> logger.warning()  # 黃色 !
log_error()    -> logger.error()    # 紅色 -
log_step()     -> logger.info()     # 藍色步驟
log_detail()   -> logger.debug()    # 灰色詳細
log_progress() -> rich.progress     # 洋紅色進度
```

### 5.2 檔案組織系統

```python
# 對應 bash 腳本的 ORGANIZE_FILES 和 setup_output_directory
class FileOrganizer:
    def __init__(self, output_dir: str, flat_mode: bool = False):
        self.output_dir = output_dir
        self.flat_mode = flat_mode

    def setup_output_path(self, base_name: str) -> Path:
        if self.flat_mode:
            return Path.cwd() / f"{base_name}.tar.zst"
        else:
            return Path(self.output_dir) / base_name / f"{base_name}.tar.zst"
```

### 5.3 分離模式壓縮

```python
# 對應 bash 的 compress_to_tar_zst (分離模式)
async def compress_archive(
    input_dir: Path,
    output_file: Path,
    level: int = 19,
    long_mode: bool = True,
    enable_check: bool = True
) -> bool:
    # 步驟1: 建立 deterministic tar
    # 步驟2: tar header 驗證
    # 步驟3: zstd 壓縮
    # 步驟4: 立即完整性驗證
    # 步驟5: 清理臨時檔案
```

### 5.4 系統資源檢查

```python
# 對應 bash 的 check_system_resources
def check_system_requirements(work_dir: Path, long_mode: bool) -> bool:
    # 記憶體檢查 (--long=31 需要 ~2.2GB)
    # 磁碟空間檢查 (2-3x 原始檔案大小)
    # CPU 核心數檢測
    # 權限檢查
```

---

## 6. CLI 介面設計

```bash
# 主要命令 (對應 bash 腳本功能)
coldstore pack [OPTIONS] [INPUT_DIR]     # 對應 archive-compress.sh
coldstore verify [OPTIONS] <FILE>        # 對應 verify-archive.sh
coldstore extract [OPTIONS] <FILE>       # 對應 extract-archive.sh
coldstore repair [OPTIONS] <FILE>        # PAR2 修復功能

# 全新整合命令
coldstore process [OPTIONS] <FILE>       # 對應 verify-and-extract.sh

# 參數支援 (對應 bash 腳本參數)
--level, -l NUM           # 壓縮等級 (1-22, 預設19)
--threads, -t NUM         # 執行緒數 (0=auto, 預設0)
--output-dir, -o DIR      # 輸出目錄 (預設 processed)
--flat                    # 扁平結構 (對應 bash --flat)
--no-long                 # 停用長距離匹配
--no-check                # 停用完整性檢查
--verbose, -v             # 詳細模式
--quiet, -q               # 安靜模式
```

---

## 7. 優化與後續

1. **多執行緒/多進程**：用 `asyncio` + `concurrent.futures` 分片壓縮。
2. **Rich TUI 模式**：即時監控壓縮進度、資源使用。
3. **設定檔支援**：`coldstore.toml` 儲存常用參數。
4. **Pipe 模式**：支援 stdin→stdout 以便串接其他工具。
5. **Large File Split**：>2 GiB 時自動分卷與獨立 PAR2。
6. **GPU 加速**：偵測 ParPar 存在時自動使用 GPU 編碼。
7. **完整性守護程序**：週期性掃描封存，記錄到 SQLite。

---

## 8. 風險與注意事項

* **跨平台 PAR2**：wheel 包雖涵蓋主流架構，但 Alpine Linux / musl 仍須自行編譯。
* **PyInstaller 衝突**：需排除 `libzstd` 重複打包；測試每個 OS 發行版。
* **記憶體管理**：大檔案時注意避免一次性讀取；以 8 MiB Chunk 為單位。
* **Rich 相容性**：確保 Windows Terminal、macOS Terminal 正確顯示彩色輸出。

---

## 9. 交接事項

* Bash 原型在 `archive-compress.sh`，**已實現完整日誌、進度、檔案組織、統計系統**。
* 現有 test fixture (小檔、損壞檔樣本) 於 `tests/fixtures/`。
* GitHub Secrets 已加入 `CODECOV_TOKEN`、`PYPI_API_TOKEN`，供發佈用。
* **重要**：Python 版本需要完全重現 bash 腳本的 UX 體驗，包括彩色輸出、進度條、統計報告。

> **下一步行動**：
>
> 1. 在 repo 建立 `feat/python-cli-baseline` 並推送骨架。
> 2. 確認 uv、CI pipeline 能順利鎖定與安裝 `par2cmdline-turbo`。
> 3. **重點**：先實現 Rich 日誌系統，確保與 bash 腳本輸出體驗一致。
> 4. 完成 M0 任務後，再開 PR 合併至 `develop`。

---

*本文件由 2025‑01‑27 微調，基於 archive-compress.sh v2.1 實際功能更新。*
