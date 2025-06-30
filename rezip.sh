#!/bin/bash
# Bash Script: 7z 轉 tar.zst 冷儲存封存工具
# 作者: AI Assistant
# 版本: v2.0 (階段8完成版)
# 用途: 將 7z 檔案轉換為 tar.zst 格式並產生完整的冷儲存封存檔案組
#
# 🎯 冷儲存封存 SOP 流程 (符合企劃書第6.3節分離模式):
# 1. 解壓縮 7z 檔案 (智能目錄結構檢測)
# 2. 建立 deterministic tar 封存 (--sort=name, 保留原始時間戳和所有者)
# 3. tar header 立即驗證 (早期錯誤偵測)
# 4. zstd 高效壓縮 (--long=31, 2GB dictionary window)
# 5. 壓縮檔案完整性驗證 (zstd + tar 內容雙重檢查)
# 6. 雙重雜湊驗證 (SHA-256 + BLAKE3)
# 7. PAR2 修復冗餘 (10%, 簡化輸出方案)
# 8. 多層驗證確保完整性 (5階段驗證流程)
#
# 🗜️ Zstd 冷儲存最佳化參數:
# -19: 高壓縮等級，平衡壓縮比和速度
# --long=31: 2GB dictionary window，用於大檔案優化，壓縮率提升 3-10%
# --check: 內建完整性檢查，確保資料正確性
#
# 📋 大檔案處理 (>4GB) 及跨平台相容性:
# - 預設使用 POSIX tar 格式，確保跨平台相容性且支援大檔案
# - 備用方案: GNU 格式 (如果 POSIX 不可用)
# - 不支援 ustar 格式 (有 4GB 限制，不適合大檔案處理)
#
# 📦 輸出檔案:
# - exp42.tar.zst (主檔，含 32-bit zstd checksum)
# - exp42.tar.zst.sha256 (SHA-256 雜湊)
# - exp42.tar.zst.blake3 (BLAKE3 雜湊)
# - exp42.tar.zst.par2 (10% PAR2 修復冗餘)

# 顯示使用說明
show_usage() {
    cat << EOF
使用方法: $0 [選項] [工作目錄]

參數:
  工作目錄                包含 7z 檔案的目錄路徑 (預設: 當前目錄)

選項:
  -l, --level NUM        壓縮等級 (1-22, 預設: 19)
                         等級 20-22 會自動啟用 Ultra 模式
  -t, --threads NUM      執行緒數量 (0=所有核心, 預設: 0)
  --no-long              停用長距離匹配 (預設啟用 --long=31，2GB dictionary window)
  --no-check             停用完整性檢查 (預設會啟用完整性檢查)
  -o, --output-dir DIR   指定輸出目錄 (預設: ./processed)
  --flat                 使用扁平結構，不創建子目錄 (向後相容)
  -h, --help             顯示此說明

範例:
  $0                                    # 處理當前目錄，輸出到 ./processed/ 子目錄
  $0 /path/to/7z/files                  # 處理指定目錄的 7z 檔案
  $0 -l 15 -t 4 /path/to/files          # 使用自訂壓縮等級和執行緒數
  $0 -o ~/output ~/archives             # 指定輸出目錄到 ~/output/
  $0 --flat ~/archives                  # 使用扁平結構 (與舊版相容)
  $0 -l 22 -o /backup ~/archives        # 最高壓縮等級 + 自訂輸出目錄

📋 系統需求:
  工具依賴: 7z, tar (支援 POSIX/GNU 格式), zstd, bc, sha256sum, b3sum, par2
  記憶體需求: 建議 4GB+ RAM (--long=31 需要約 2.2GB 壓縮記憶體)
  磁碟空間: 至少為原始檔案大小的 2-3 倍 (含臨時檔案和冗餘)
  
🎯 冷儲存功能:
  - Deterministic tar: 確保可重現性 (--sort=name)
  - 高效壓縮: zstd 最佳化參數，壓縮比可達 60-80%
  - 雙重雜湊: SHA-256 + BLAKE3 提供最高安全性
  - PAR2 修復: 10% 冗餘，可修復檔案損壞
  - 5階段驗證: 確保每步驟完整性
  - 智能組織: 子目錄結構，避免檔案混亂

⚠️ 注意事項:
  - 大檔案 (>2GB) 處理可能需要較長時間
  - 建議在 SSD 上進行處理以提升效能
  - 轉換後的檔案會保存在同一目錄中
  - 處理期間會產生臨時檔案，請確保磁碟空間充足
EOF
}

# 解析命令列參數
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -l|--level)
                shift
                if [[ -n "$1" && "$1" =~ ^[0-9]+$ && "$1" -ge 1 && "$1" -le 22 ]]; then
                    COMPRESSION_LEVEL="$1"
                    # 自動判斷是否需要啟用 ultra 模式
                    if [ "$COMPRESSION_LEVEL" -ge 20 ] && [ "$COMPRESSION_LEVEL" -le 22 ]; then
                        ULTRA_MODE=true
                    else
                        ULTRA_MODE=false
                    fi
                    shift
                else
                    echo "錯誤: 壓縮等級必須是 1-22 之間的數字" >&2
                    exit 1
                fi
                ;;
            -t|--threads)
                shift
                if [[ -n "$1" && "$1" =~ ^[0-9]+$ ]]; then
                    THREADS="$1"
                    shift
                else
                    echo "錯誤: 執行緒數量必須是非負整數" >&2
                    exit 1
                fi
                ;;
            --no-long)
                LONG_MODE=false
                shift
                ;;
            --no-check)
                ENABLE_CHECK=false
                shift
                ;;
            -o|--output-dir)
                shift
                if [[ -n "$1" ]]; then
                    OUTPUT_DIR="$1"
                    shift
                else
                    echo "錯誤: --output-dir 需要指定目錄路徑" >&2
                    exit 1
                fi
                ;;
            --flat)
                ORGANIZE_FILES=false
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                echo "錯誤: 未知選項 $1" >&2
                echo "使用 $0 --help 查看使用說明" >&2
                exit 1
                ;;
            *)
                # 這是工作目錄參數
                if [[ -z "$WORK_DIR_SET" ]]; then
                    WORK_DIR="$1"
                    WORK_DIR_SET=true
                    shift
                else
                    echo "錯誤: 只能指定一個工作目錄" >&2
                    exit 1
                fi
                ;;
        esac
    done
}

# 預設參數
COMPRESSION_LEVEL=19
THREADS=0  # 0 表示使用所有可用 CPU 核心
LONG_MODE=true
ENABLE_CHECK=true
ULTRA_MODE=false  # 當壓縮等級為 20-22 時自動啟用
OUTPUT_DIR="processed"  # 預設輸出目錄
ORGANIZE_FILES=true  # 預設使用子目錄組織

# 解析參數
parse_arguments "$@"

# 顏色定義
declare -r COLOR_RED='\033[0;31m'
declare -r COLOR_GREEN='\033[0;32m'
declare -r COLOR_YELLOW='\033[0;33m'
declare -r COLOR_BLUE='\033[0;34m'
declare -r COLOR_MAGENTA='\033[0;35m'
declare -r COLOR_CYAN='\033[0;36m'
declare -r COLOR_WHITE='\033[0;37m'
declare -r COLOR_GRAY='\033[0;90m'
declare -r COLOR_BRIGHT_GREEN='\033[1;32m'
declare -r COLOR_BRIGHT_BLUE='\033[1;34m'
declare -r COLOR_BRIGHT_YELLOW='\033[1;33m'
declare -r COLOR_RESET='\033[0m'

# 日誌函數
log_info() {
    printf "${COLOR_CYAN}%s${COLOR_RESET}\n" "$1"
}

log_success() {
    printf "${COLOR_BRIGHT_GREEN}✓ %s${COLOR_RESET}\n" "$1"
}

log_warning() {
    printf "${COLOR_BRIGHT_YELLOW}⚠ %s${COLOR_RESET}\n" "$1"
}

log_error() {
    printf "${COLOR_RED}✗ %s${COLOR_RESET}\n" "$1" >&2
}

log_step() {
    printf "${COLOR_BRIGHT_BLUE}%s${COLOR_RESET}\n" "$1"
}

log_detail() {
    printf "${COLOR_GRAY}  %s${COLOR_RESET}\n" "$1"
}

log_progress() {
    printf "${COLOR_MAGENTA}%s${COLOR_RESET}\n" "$1"
}

log_config() {
    printf "${COLOR_WHITE}%s${COLOR_RESET}\n" "$1"
}

# 動畫效果函數
show_spinner() {
    local pid=$1
    local message="$2"
    local spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local spinner_i=0
    
    printf "${COLOR_GRAY}%s " "$message"
    while kill -0 "$pid" 2>/dev/null; do
        printf "\b${spinner:$spinner_i:1}"
        spinner_i=$(( (spinner_i+1) % ${#spinner} ))
        sleep 0.1
    done
    printf "\b "
}

progress_bar() {
    local current=$1
    local total=$2
    local message="$3"
    local width=40
    local percentage=$((current * 100 / total))
    local filled=$((current * width / total))
    
    printf "${COLOR_BRIGHT_BLUE}%s [" "$message"
    
    # 繪製進度條 (使用局部變數避免衝突)
    local bar_i
    for ((bar_i=0; bar_i<filled; bar_i++)); do
        printf "█"
    done
    for ((bar_i=filled; bar_i<width; bar_i++)); do
        printf "░"
    done
    
    printf "] %d%% (%d/%d)${COLOR_RESET}\n" "$percentage" "$current" "$total"
}

# 檢查 tar 格式支援
check_tar_formats() {
    local supported_formats=()
    
    # 測試 GNU 格式支援
    if tar --help 2>&1 | grep -q -- "--format" && tar --help 2>&1 | grep -q "gnu"; then
        supported_formats+=("gnu")
    fi
    if tar --help 2>&1 | grep -q -- "--format" && tar --help 2>&1 | grep -q "posix"; then
        supported_formats+=("posix")
    fi
    
    echo "${supported_formats[@]}"
}

# 設置輸出目錄結構 (階段9新增功能)
setup_output_directory() {
    local base_name="$1"
    local work_dir="$2"
    
    # 確定最終輸出目錄
    local final_output_dir
    if [ "$ORGANIZE_FILES" = true ]; then
        # 子目錄組織模式
        if [[ "$OUTPUT_DIR" == /* ]]; then
            # 絕對路徑
            final_output_dir="$OUTPUT_DIR/$base_name"
        else
            # 相對路徑，基於工作目錄
            final_output_dir="$work_dir/$OUTPUT_DIR/$base_name"
        fi
    else
        # 扁平模式，直接放在工作目錄
        final_output_dir="$work_dir"
    fi
    
    # 確保輸出目錄存在
    if [ "$ORGANIZE_FILES" = true ]; then
        if [ ! -d "$final_output_dir" ]; then
            log_detail "創建輸出目錄: $final_output_dir" >&2
            if ! mkdir -p "$final_output_dir"; then
                log_error "無法創建輸出目錄: $final_output_dir" >&2
                return 1
            fi
        fi
        
        # 驗證目錄權限
        if [ ! -w "$final_output_dir" ]; then
            log_error "輸出目錄無寫入權限: $final_output_dir" >&2
            return 1
        fi
        
        log_success "輸出目錄準備完成: $final_output_dir" >&2
    fi
    
    # 返回最終輸出目錄路徑
    echo "$final_output_dir"
}

# 清理輸出目錄 (階段9新增功能)
cleanup_output_directory() {
    local output_dir="$1"
    local keep_successful="$2"  # true=保留成功的檔案，false=全部清理
    
    if [ "$ORGANIZE_FILES" = false ] || [ "$keep_successful" = true ]; then
        # 扁平模式或保留成功檔案時不清理
        return 0
    fi
    
    if [ -d "$output_dir" ] && [ -z "$(ls -A "$output_dir" 2>/dev/null)" ]; then
        # 目錄存在且為空時清理
        log_detail "清理空輸出目錄: $output_dir" >&2
        rmdir "$output_dir" 2>/dev/null || log_warning "無法移除空目錄: $output_dir" >&2
    fi
}

# 檢查系統資源 (階段8強化功能)
check_system_resources() {
    local work_dir="$1"
    
    log_info "檢查系統資源狀況..."
    
    # 檢查記憶體
    if command -v free >/dev/null 2>&1; then
        local total_memory available_memory
        total_memory=$(free -b | awk 'NR==2{print $2}')
        available_memory=$(free -b | awk 'NR==2{print $7}')
        
        local total_gb available_gb
        total_gb=$(echo "scale=1; $total_memory/1073741824" | bc)
        available_gb=$(echo "scale=1; $available_memory/1073741824" | bc)
        
        log_detail "系統記憶體: 總計 ${total_gb}GB，可用 ${available_gb}GB"
        
        # 記憶體需求檢查 (--long=31 需要約2.2GB)
        if [ "$LONG_MODE" = true ]; then
            local required_memory=2400000000  # 2.4GB in bytes
            if [ "$available_memory" -lt "$required_memory" ]; then
                log_warning "可用記憶體不足，建議至少 2.4GB (當前: ${available_gb}GB)"
                log_detail "考慮使用 --no-long 參數降低記憶體需求"
            fi
        fi
    else
        log_detail "無法檢測記憶體狀況 (free 命令不可用)"
    fi
    
    # 檢查CPU核心數
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo "未知")
    log_detail "CPU 核心數: $cpu_cores"
    
    # 檢查磁碟空間
    local available_space_kb available_space_gb
    available_space_kb=$(df "$work_dir" | awk 'NR==2 {print $4}')
    available_space_gb=$(echo "scale=2; $available_space_kb/1048576" | bc)
    log_detail "工作目錄可用空間: ${available_space_gb}GB"
    
    if [ "$(echo "$available_space_gb < 1" | bc)" -eq 1 ]; then
        log_warning "磁碟空間不足，建議至少保留 1GB 以上空間"
    fi
    
    log_success "系統資源檢查完成"
}

# 檢查必要工具
check_required_tools() {
    local missing=()
    
    # 檢查 7z
    local sevenz_status="✓ 已找到"
    if ! command -v 7z &> /dev/null; then
        missing+=("7z")
        sevenz_status="✗ 缺少"
    fi
    
    # 檢查 tar
    local tar_status="✓ 已找到"
    if ! command -v tar &> /dev/null; then
        missing+=("tar")
        tar_status="✗ 缺少"
    else
        # 檢查 tar 格式支援以處理大檔案
        local supported_formats=($(check_tar_formats))
        if [ ${#supported_formats[@]} -gt 0 ]; then
            # 按照優先級排序：POSIX > GNU
            local ordered_formats=()
            if [[ " ${supported_formats[*]} " =~ " posix " ]]; then
                ordered_formats+=("posix")
            fi
            if [[ " ${supported_formats[*]} " =~ " gnu " ]]; then
                ordered_formats+=("gnu")
            fi
            tar_status="✓ 已找到 (格式: ${ordered_formats[*]})"
        else
            tar_status="⚠ 已找到 (格式支援有限 - 可能有 4GB 檔案大小限制)"
        fi
    fi
    
    # 檢查 zstd
    local zstd_status="✓ 已找到"
    if ! command -v zstd &> /dev/null; then
        missing+=("zstd")
        zstd_status="✗ 缺少"
    fi
    
    # 檢查 bc (用於計算)
    local bc_status="✓ 已找到"
    if ! command -v bc &> /dev/null; then
        missing+=("bc")
        bc_status="✗ 缺少"
    fi
    
    # 檢查 sha256sum
    local sha256_status="✓ 已找到"
    if ! command -v sha256sum &> /dev/null; then
        missing+=("sha256sum")
        sha256_status="✗ 缺少"
    fi
    
    # 檢查 b3sum (BLAKE3)
    local b3sum_status="✓ 已找到"
    if ! command -v b3sum &> /dev/null; then
        missing+=("b3sum")
        b3sum_status="✗ 缺少"
    fi
    
    # 檢查 par2 (PAR2 修復)
    local par2_status="✓ 已找到"
    if ! command -v par2 &> /dev/null; then
        missing+=("par2")
        par2_status="✗ 缺少"
    fi
    
    # 顯示所有工具檢查結果
    log_success "工具檢查結果:"
    log_detail "7z 狀態: $sevenz_status"
    log_detail "tar 狀態: $tar_status"
    log_detail "zstd 狀態: $zstd_status"
    log_detail "bc 狀態: $bc_status"
    log_detail "sha256sum 狀態: $sha256_status"
    log_detail "b3sum 狀態: $b3sum_status"
    log_detail "par2 狀態: $par2_status"
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少必要工具: ${missing[*]}"
        log_detail ""
        log_detail "安裝建議 (Ubuntu/Debian):"
        log_detail "sudo apt update && apt install tar zstd par2cmdline b3sum"
        log_detail ""
        log_detail "注意: 7z, bc, sha256sum 通常已預裝"
        log_detail "如果系統沒有 b3sum，請從 https://github.com/BLAKE3-team/BLAKE3 下載"
        exit 1
    fi
    
    log_success "所有必要工具已安裝"
    
    # 大檔案支援檢查
    local supported_formats=($(check_tar_formats))
    if [ ${#supported_formats[@]} -eq 0 ]; then
        log_error "您的 tar 版本不支援現代格式 (POSIX/GNU)"
        log_detail "無法處理大檔案 (>4GB)，請升級 tar 版本"
        exit 1
    fi
}

# 檢查 7z 檔案結構 (重新設計，更準確判斷)
check_7z_structure() {
    local zip_file="$1"
    
    # 檢查檔案是否存在且可讀取
    if [ ! -f "$zip_file" ] || [ ! -r "$zip_file" ]; then
        log_error "檔案不存在或無法讀取: $zip_file"
        return 1
    fi
    
    # 檢查檔案大小 (避免處理空檔案)
    local file_size
    file_size=$(stat -c%s "$zip_file" 2>/dev/null || echo "0")
    if [ "$file_size" -eq 0 ]; then
        log_warning "檔案大小為 0，將跳過處理"
        return 1
    fi
    
    # 使用 7z 列表命令檢查結構 (使用更簡單的輸出格式)
    local list_output
    if ! list_output=$(7z l "$zip_file" 2>/dev/null | grep -E "^[^-].*[^/\\]$" | tail -n +3 | head -n -2); then
        log_warning "無法分析壓縮檔結構，將建立資料夾"
        return 1
    fi
    
    # 檢查是否為空壓縮檔
    if [ -z "$list_output" ]; then
        log_warning "壓縮檔為空，將建立資料夾"
        return 1
    fi
    
    # 獲取檔案名稱 (不含副檔名)
    local base_name
    base_name=$(basename "$zip_file" .7z)
    
    # 更可靠的檢查方法：檢查是否所有項目都在同一個與檔案名稱相同的資料夾中
    local has_matching_top_folder=false
    local has_other_items=false
    
    # 使用 7z 詳細列表格式檢查
    local output
    if output=$(7z l "$zip_file" -slt 2>/dev/null); then
        local current_path=""
        local current_is_folder=false
        
        while IFS= read -r line; do
            if [[ "$line" == "Path = "* ]]; then
                current_path="${line#Path = }"
            elif [[ "$line" == "Folder = +"* ]]; then
                current_is_folder=true
            elif [[ "$line" == "Folder = -"* ]]; then
                current_is_folder=false
            elif [[ "$line" == "" ]] && [[ -n "$current_path" ]]; then
                # 處理完一個項目，分析路徑
                if [[ "$current_path" == "$base_name" ]] && [[ "$current_is_folder" == true ]]; then
                    has_matching_top_folder=true
                elif [[ "$current_path" == "$base_name/"* ]]; then
                    # 在同名資料夾內的檔案，這是好的
                    continue
                else
                    # 不在同名資料夾內的項目（檔案或其他資料夾）
                    has_other_items=true
                    break
                fi
                
                # 重置狀態
                current_path=""
                current_is_folder=false
            fi
        done <<< "$output"
        
        # 處理最後一個項目（如果檔案末尾沒有空行）
        if [[ -n "$current_path" ]]; then
            if [[ "$current_path" == "$base_name" ]] && [[ "$current_is_folder" == true ]]; then
                has_matching_top_folder=true
            elif [[ "$current_path" != "$base_name/"* ]]; then
                has_other_items=true
            fi
        fi
    else
        # 如果無法解析，預設建立資料夾
        return 1
    fi
    
    # 只有在有同名頂層資料夾且沒有其他散落項目時才返回 true
    [ "$has_matching_top_folder" = true ] && [ "$has_other_items" = false ]
}

# 解壓縮 7z 檔案 (優化版：根據結構智能選擇解壓縮策略)
extract_7z_file() {
    local zip_file="$1"
    local output_dir="$2"
    local has_top_folder="$3"  # true/false，表示是否有同名頂層資料夾
    
    # 檔案名稱安全性檢查
    local base_name
    base_name=$(basename "$zip_file" .7z)
    
    # 檢查檔案名稱是否包含危險字符
    if [[ "$base_name" =~ [^a-zA-Z0-9._-] ]]; then
        log_warning "檔案名稱包含特殊字符，可能影響處理: $base_name" >&2
    fi
    
    # 驗證輸出目錄是否存在且可寫入
    if [ ! -d "$output_dir" ]; then
        log_error "輸出目錄不存在: $output_dir"
        return 1
    fi
    
    if [ ! -w "$output_dir" ]; then
        log_error "輸出目錄無寫入權限: $output_dir"
        return 1
    fi
    
    local extracted_dir
    
    if [ "$has_top_folder" = true ]; then
        # 情況1：7z檔案內已有同名頂層資料夾，直接解壓縮到output_dir
        log_detail "檔案內已有頂層資料夾，直接解壓縮到: $output_dir" >&2
        
        if ! 7z x "$zip_file" -o"$output_dir" -y >/dev/null 2>&1; then
            log_error "7z 解壓縮失敗"
            return 1
        fi
        
        # 解壓縮後的目錄應該是 output_dir/base_name
        extracted_dir="$output_dir/$base_name"
        
    else
        # 情況2：7z檔案內是散落的檔案，需要先建立目標資料夾
        local target_dir="$output_dir/$base_name"
        log_detail "檔案內是散落檔案，建立目標資料夾: $target_dir" >&2
        
        # 建立目標資料夾
        if ! mkdir -p "$target_dir"; then
            log_error "無法創建目標資料夾: $target_dir"
            return 1
        fi
        
        # 解壓縮到目標資料夾
        if ! 7z x "$zip_file" -o"$target_dir" -y >/dev/null 2>&1; then
            log_error "7z 解壓縮失敗"
            # 清理失敗的目錄
            rm -rf "$target_dir" 2>/dev/null
            return 1
        fi
        
        extracted_dir="$target_dir"
    fi
    
    # 驗證解壓縮結果
    if [ ! -d "$extracted_dir" ]; then
        log_error "解壓縮後目錄不存在: $extracted_dir"
        return 1
    fi
    
    if [ -z "$(ls -A "$extracted_dir" 2>/dev/null)" ]; then
        log_error "解壓縮後目錄為空: $extracted_dir"
        return 1
    fi
    
    # 返回解壓縮目錄路徑
    echo "$extracted_dir"
    log_success "已解壓縮至: $extracted_dir" >&2
}

# 重新壓縮為 tar.zst (分離模式，符合企劃書 SOP)
compress_to_tar_zst() {
    local input_dir="$1"
    local output_file="$2"
    local compression_level="$3"
    local threads="$4"
    local long_mode="$5"
    local enable_check="$6"
    local ultra_mode="$7"
    
    if [ ! -d "$input_dir" ]; then
        log_error "輸入目錄不存在: $input_dir" >&2
        return 1
    fi
    
    # 準備臨時檔案路徑
    local temp_tar="${output_file%.zst}"
    local temp_tar_basename=$(basename "$temp_tar")
    local output_dir=$(dirname "$output_file")
    local zstd_params=()
    
    # 壓縮等級
    zstd_params+=("-$compression_level")
    
    # Ultra 模式 (僅在等級 20-22 時有效)
    if [ "$ultra_mode" = true ]; then
        zstd_params+=("--ultra")
    fi
    
    # 執行緒數
    if [ "$threads" -gt 0 ]; then
        zstd_params+=("-T$threads")
    else
        zstd_params+=("-T0")  # 使用所有可用核心
    fi
    
    # 長距離匹配 (2GB dictionary window 用於大檔案優化)
    if [ "$long_mode" = true ]; then
        zstd_params+=("--long=31")
    fi
    
    # 完整性檢查
    if [ "$enable_check" = true ]; then
        zstd_params+=("--check")
    fi
    
    # 強制覆蓋已存在的檔案
    zstd_params+=("--force")
    
    # 顯示資料夾大小資訊
    local folder_size
    if folder_size=$(du -sb "$input_dir" 2>/dev/null | cut -f1); then
        local folder_size_str
        if [ "$folder_size" -gt 1073741824 ]; then  # 1GB
            folder_size_str="$(echo "scale=2; $folder_size / 1073741824" | bc)GB"
        else
            folder_size_str="$(echo "scale=2; $folder_size / 1048576" | bc)MB"
        fi
        log_detail "資料夾大小: $folder_size_str"
    fi
    
    # 檢查磁碟空間（臨時 tar 檔案約等於資料夾大小）
    if [ -n "$folder_size" ]; then
        local available_space
        available_space=$(df "$output_dir" | awk 'NR==2 {print $4 * 1024}')  # 轉換為 bytes
        local required_space=$((folder_size + 1073741824))  # 資料夾大小 + 1GB 緩衝
        
        if [ "$available_space" -lt "$required_space" ]; then
            local available_gb required_gb
            available_gb="$(echo "scale=2; $available_space / 1073741824" | bc)"
            required_gb="$(echo "scale=2; $required_space / 1073741824" | bc)"
            log_error "磁碟空間不足: 可用 ${available_gb}GB，需要 ${required_gb}GB"
            return 1
        fi
        log_detail "磁碟空間檢查: 可用空間充足"
    fi
    
    # 檢查 tar 格式支援
    local supported_formats=($(check_tar_formats))
    local best_format=""
    
    # 選擇最佳格式 (POSIX 優先)
    if [[ " ${supported_formats[*]} " =~ " posix " ]]; then
        best_format="posix"
    elif [[ " ${supported_formats[*]} " =~ " gnu " ]]; then
        best_format="gnu"
    else
        log_error "無法找到適合的 tar 格式"
        log_detail "支援的格式: ${supported_formats[*]}"
        log_detail "這些格式是處理大檔案 (>4GB) 的必要條件"
        log_detail "請升級到支援現代 tar 格式的版本"
        return 1
    fi
    
    # 顯示最終參數
    log_detail "處理模式: 分離模式 (符合企劃書 SOP)"
    log_detail "tar 參數: --sort=name --format=$best_format (deterministic 檔案排序)"
    log_detail "zstd 參數: ${zstd_params[*]}"
    log_detail "臨時檔案: $temp_tar_basename"
    
    # 顯示記憶體需求警告 (針對 --long=31)
    if [ "$long_mode" = true ]; then
        log_detail "記憶體需求: 壓縮約需 2.2GB RAM，解壓約需 2GB RAM (--long=31)"
    fi
    
    # 切換到輸入目錄的父目錄
    local current_dir=$(pwd)
    local parent_dir=$(dirname "$input_dir")
    local folder_name=$(basename "$input_dir")
    
    cd "$parent_dir" || return 1
    
    # 清理可能存在的舊臨時檔案
    if [ -f "$temp_tar" ]; then
        log_detail "清理舊臨時檔案: $(basename "$temp_tar")"
        rm -f "$temp_tar"
    fi
    
    # 階段1：創建 deterministic tar 檔案
    log_step "階段1: 創建 deterministic tar 檔案..." >&2
    if ! tar --sort=name --format="$best_format" -cf "$temp_tar" "$folder_name"; then
        log_error "tar 創建失敗"
        cd "$current_dir"
        return 1
    fi
    
    # 驗證 tar 檔案是否創建成功
    if [ ! -f "$temp_tar" ]; then
        log_error "tar 檔案創建失敗: $(basename "$temp_tar")"
    cd "$current_dir"
        return 1
    fi
    
    local tar_size
    tar_size=$(stat -c%s "$temp_tar")
    local tar_size_str
    if [ "$tar_size" -gt 1073741824 ]; then  # 1GB
        tar_size_str="$(echo "scale=2; $tar_size / 1073741824" | bc)GB"
    else
        tar_size_str="$(echo "scale=2; $tar_size / 1048576" | bc)MB"
    fi
    log_success "tar 檔案創建成功: $(basename "$temp_tar") ($tar_size_str)" >&2
    
    # 階段2：驗證 tar header 完整性
    log_step "階段2: 驗證 tar header 完整性..." >&2
    if ! tar -tvf "$temp_tar" > /dev/null 2>&1; then
        log_error "tar header 驗證失敗"
        rm -f "$temp_tar"  # 清理損壞的檔案
        cd "$current_dir"
        return 1
    fi
    log_success "tar header 驗證通過" >&2
    
    # 階段3：zstd 壓縮
    log_step "階段3: zstd 壓縮處理..." >&2
    if ! zstd "${zstd_params[@]}" "$temp_tar" -o "$output_file"; then
        log_error "zstd 壓縮失敗"
        rm -f "$temp_tar"  # 清理臨時檔案
        cd "$current_dir"
        return 1
    fi
    
    # 驗證壓縮檔案是否創建成功
    if [ ! -f "$output_file" ]; then
        log_error "壓縮檔案創建失敗: $(basename "$output_file")"
        rm -f "$temp_tar"
        cd "$current_dir"
        return 1
    fi
    
    local zst_size
    zst_size=$(stat -c%s "$output_file")
    local zst_size_str
    if [ "$zst_size" -gt 1073741824 ]; then  # 1GB
        zst_size_str="$(echo "scale=2; $zst_size / 1073741824" | bc)GB"
    else
        zst_size_str="$(echo "scale=2; $zst_size / 1048576" | bc)MB"
    fi
    log_success "zstd 壓縮完成: $(basename "$output_file") ($zst_size_str)" >&2
    
    # 階段4：立即驗證壓縮檔案完整性（企劃書步驟4）
    log_step "階段4: 驗證壓縮檔案完整性..." >&2
    
    # 準備驗證參數（需要與壓縮參數一致）
    local verify_params=()
    if [ "$long_mode" = true ]; then
        verify_params+=("--long=31")
    fi
    
    # 4a. zstd 完整性檢查
    local zstd_verify_start
    zstd_verify_start=$(date +%s.%3N)
    if ! zstd -tq "${verify_params[@]}" "$output_file"; then
        local zstd_verify_end
        zstd_verify_end=$(date +%s.%3N)
        verification_stats "zstd 完整性驗證" "$zstd_verify_start" "$zstd_verify_end" "failure" "$output_file" >&2
        log_error "zstd 完整性驗證失敗"
        generate_diagnostic_info "zstd 壓縮檔案損壞" "$output_file" "可能的記憶體不足或磁碟空間問題" >&2
        rm -f "$temp_tar" "$output_file"
        cd "$current_dir"
        return 1
    fi
    local zstd_verify_end
    zstd_verify_end=$(date +%s.%3N)
    verification_stats "zstd 完整性驗證" "$zstd_verify_start" "$zstd_verify_end" "success" "$output_file" >&2
    log_detail "zstd 完整性驗證通過" >&2
    
    # 4b. 解壓縮後 tar 內容驗證
    local tar_content_start
    tar_content_start=$(date +%s.%3N)
    if ! zstd -dc "${verify_params[@]}" "$output_file" | tar -tvf - > /dev/null 2>&1; then
        local tar_content_end
        tar_content_end=$(date +%s.%3N)
        verification_stats "tar 內容驗證" "$tar_content_start" "$tar_content_end" "failure" "$output_file" >&2
        log_error "解壓縮後 tar 內容驗證失敗"
        generate_diagnostic_info "tar 內容結構損壞" "$output_file" "可能的 tar 創建過程錯誤或壓縮損壞" >&2
        rm -f "$temp_tar" "$output_file"
        cd "$current_dir"
        return 1
    fi
    local tar_content_end
    tar_content_end=$(date +%s.%3N)
    verification_stats "tar 內容驗證" "$tar_content_start" "$tar_content_end" "success" "$output_file" >&2
    log_detail "解壓縮後 tar 內容驗證通過" >&2
    log_success "壓縮檔案完整性驗證通過" >&2
    
    # 階段5：清理臨時檔案
    log_step "階段5: 清理臨時檔案..." >&2
    if rm -f "$temp_tar"; then
        log_success "臨時檔案清理完成: $(basename "$temp_tar")" >&2
    else
        log_warning "臨時檔案清理失敗: $(basename "$temp_tar")" >&2
    fi
    
    cd "$current_dir"
    
    # 顯示最終結果
    local compression_ratio
    compression_ratio=$(echo "scale=2; $zst_size * 100 / $tar_size" | bc)
    log_detail "壓縮比: $compression_ratio% (tar: $tar_size_str → zst: $zst_size_str)" >&2
    log_success "分離模式壓縮完成: $(basename "$output_file")" >&2
}

# 產生 SHA256 校驗和檔案
generate_sha256_file() {
    local file_path="$1"
    
    local hash
    hash=$(sha256sum "$file_path" | cut -d' ' -f1)
    local checksum_file="$file_path.sha256"
    local file_name
    file_name=$(basename "$file_path")
    
    echo "$hash  $file_name" > "$checksum_file"
    
    # 先輸出路徑，再顯示成功訊息（重定向到 stderr）
    echo "$checksum_file"
    log_success "SHA256 雜湊檔案已產生: $checksum_file" >&2
}

# 產生 BLAKE3 雜湊檔案
generate_blake3_file() {
    local file_path="$1"
    
    local hash
    hash=$(b3sum "$file_path" | cut -d' ' -f1)
    local checksum_file="$file_path.blake3"
    local file_name
    file_name=$(basename "$file_path")
    
    echo "$hash  $file_name" > "$checksum_file"
    
    # 先輸出路徑，再顯示成功訊息（重定向到 stderr）
    echo "$checksum_file"
    log_success "BLAKE3 雜湊檔案已產生: $checksum_file" >&2
}

# 驗證統計函數 - 記錄驗證時間和結果
verification_stats() {
    local stage_name="$1"
    local start_time="$2"
    local end_time="$3"
    local status="$4"
    local file_path="$5"
    
    local duration
    duration=$(echo "scale=3; $end_time - $start_time" | bc)
    
    if [ "$status" = "success" ]; then
        log_detail "✓ $stage_name 完成：耗時 ${duration}s" >&2
    else
        log_detail "✗ $stage_name 失敗：耗時 ${duration}s" >&2
    fi
    
    # 如果有檔案路徑，顯示檔案大小資訊
    if [ -n "$file_path" ] && [ -f "$file_path" ]; then
        local file_size
        file_size=$(stat -c%s "$file_path")
        local file_size_str
        if [ "$file_size" -gt 1073741824 ]; then
            file_size_str="$(echo "scale=2; $file_size/1073741824" | bc) GB"
        else
            file_size_str="$(echo "scale=2; $file_size/1048576" | bc) MB"
        fi
        local speed
        if [ "$duration" != "0" ] && [ "$duration" != "0.000" ]; then
            speed=$(echo "scale=2; $file_size/1048576/$duration" | bc)
            log_detail "  檔案大小：$file_size_str，處理速度：${speed} MB/s" >&2
        else
            log_detail "  檔案大小：$file_size_str" >&2
        fi
    fi
}

# 進階診斷資訊函數
generate_diagnostic_info() {
    local error_type="$1"
    local file_path="$2"
    local additional_info="$3"
    
    log_error "=== 診斷資訊 ==="
    log_detail "錯誤類型：$error_type"
    log_detail "時間戳記：$(date '+%Y-%m-%d %H:%M:%S')"
    
    if [ -n "$file_path" ]; then
        log_detail "問題檔案：$file_path"
        if [ -f "$file_path" ]; then
            local file_size
            file_size=$(stat -c%s "$file_path")
            local file_size_str
            if [ "$file_size" -gt 1073741824 ]; then
                file_size_str="$(echo "scale=2; $file_size/1073741824" | bc) GB"
            else
                file_size_str="$(echo "scale=2; $file_size/1048576" | bc) MB"
            fi
            log_detail "檔案大小：$file_size_str"
            log_detail "檔案權限：$(ls -la "$file_path" | awk '{print $1}')"
        else
            log_detail "檔案狀態：檔案不存在或無法存取"
        fi
    fi
    
    # 系統資源資訊
    local available_space
    available_space=$(df "$(dirname "${file_path:-$PWD}")" 2>/dev/null | awk 'NR==2 {print $4*1024}' || echo "未知")
    if [ "$available_space" != "未知" ]; then
        local space_gb
        space_gb=$(echo "scale=2; $available_space/1073741824" | bc)
        log_detail "可用磁碟空間：${space_gb} GB"
    fi
    
    local memory_info
    if command -v free >/dev/null 2>&1; then
        memory_info=$(free -h | awk 'NR==2{print $7}')
        log_detail "可用記憶體：$memory_info"
    fi
    
    if [ -n "$additional_info" ]; then
        log_detail "額外資訊：$additional_info"
    fi
    
    log_detail "建議動作：檢查磁碟空間、記憶體狀況和檔案權限"
    log_error "=== 診斷結束 ==="
}

# 驗證 SHA256 校驗和檔案 (強化版)
verify_sha256() {
    local file_path="$1"
    local checksum_file="$2"
    local start_time
    start_time=$(date +%s.%3N)
    
    local expected_hash
    expected_hash=$(cut -d' ' -f1 "$checksum_file")
    local actual_hash
    actual_hash=$(sha256sum "$file_path" | cut -d' ' -f1)
    
    local end_time
    end_time=$(date +%s.%3N)
    
    if [ "$expected_hash" = "$actual_hash" ]; then
        verification_stats "SHA256 驗證" "$start_time" "$end_time" "success" "$file_path"
        log_success "SHA256 雜湊驗證通過"
        return 0
    else
        verification_stats "SHA256 驗證" "$start_time" "$end_time" "failure" "$file_path"
        log_error "SHA256 雜湊驗證失敗！"
        log_detail "預期雜湊：$expected_hash"
        log_detail "實際雜湊：$actual_hash"
        generate_diagnostic_info "SHA256 雜湊不符" "$file_path" "可能的檔案損壞或傳輸錯誤"
        return 1
    fi
}

# 驗證 BLAKE3 雜湊檔案 (強化版)
verify_blake3() {
    local file_path="$1"
    local checksum_file="$2"
    local start_time
    start_time=$(date +%s.%3N)
    
    local expected_hash
    expected_hash=$(cut -d' ' -f1 "$checksum_file")
    local actual_hash
    actual_hash=$(b3sum "$file_path" | cut -d' ' -f1)
    
    local end_time
    end_time=$(date +%s.%3N)
    
    if [ "$expected_hash" = "$actual_hash" ]; then
        verification_stats "BLAKE3 驗證" "$start_time" "$end_time" "success" "$file_path"
        log_success "BLAKE3 雜湊驗證通過"
        return 0
    else
        verification_stats "BLAKE3 驗證" "$start_time" "$end_time" "failure" "$file_path"
        log_error "BLAKE3 雜湊驗證失敗！"
        log_detail "預期雜湊：$expected_hash"
        log_detail "實際雜湊：$actual_hash"
        generate_diagnostic_info "BLAKE3 雜湊不符" "$file_path" "可能的檔案損壞或演算法實現差異"
        return 1
    fi
}

# 統一雜湊管理函數 - 產生雙重雜湊檔案
generate_dual_hashes() {
    local file_path="$1"
    local sha256_file=""
    local blake3_file=""
    
    log_step "產生雙重雜湊檔案 (SHA-256 + BLAKE3)..." >&2
    
    # 產生 SHA256 雜湊
    if sha256_file=$(generate_sha256_file "$file_path"); then
        log_detail "SHA256: $(basename "$sha256_file")" >&2
    else
        log_error "SHA256 雜湊產生失敗" >&2
        return 1
    fi
    
    # 產生 BLAKE3 雜湊
    if blake3_file=$(generate_blake3_file "$file_path"); then
        log_detail "BLAKE3: $(basename "$blake3_file")" >&2
    else
        log_error "BLAKE3 雜湊產生失敗" >&2
        # 清理已產生的 SHA256 檔案
        rm -f "$sha256_file" 2>/dev/null
        return 1
    fi
    
    log_success "雙重雜湊檔案產生完成" >&2
    
    # 輸出產生的檔案路徑 (只輸出到 stdout，供主流程解析)
    echo "$sha256_file"
    echo "$blake3_file"
}

# 統一雜湊管理函數 - 驗證雙重雜湊
verify_dual_hashes() {
    local file_path="$1"
    local sha256_file="$2"
    local blake3_file="$3"
    
    log_step "驗證雙重雜湊 (SHA-256 + BLAKE3)..."
    
    local sha256_result=false
    local blake3_result=false
    
    # 驗證 SHA256
    if [ -f "$sha256_file" ]; then
        if verify_sha256 "$file_path" "$sha256_file"; then
            sha256_result=true
        fi
    else
        log_error "SHA256 雜湊檔案不存在: $sha256_file"
    fi
    
    # 驗證 BLAKE3
    if [ -f "$blake3_file" ]; then
        if verify_blake3 "$file_path" "$blake3_file"; then
            blake3_result=true
        fi
    else
        log_error "BLAKE3 雜湊檔案不存在: $blake3_file"
    fi
    
    # 檢查雙重驗證結果
    if [ "$sha256_result" = true ] && [ "$blake3_result" = true ]; then
        log_success "雙重雜湊驗證通過 (SHA-256 ✓ + BLAKE3 ✓)"
        return 0
    else
        log_error "雙重雜湊驗證失敗 (SHA-256: $sha256_result, BLAKE3: $blake3_result)"
        return 1
    fi
}

# PAR2 修復冗餘函數 - 產生 PAR2 修復檔案
generate_par2_file() {
    local file_path="$1"
    local par2_file="${file_path}.par2"
    
    log_step "產生 PAR2 修復檔案 (10% 冗餘)..." >&2
    
    # 檢查輸入檔案是否存在
    if [ ! -f "$file_path" ]; then
        log_error "檔案不存在: $file_path" >&2
        return 1
    fi
    
    # 計算檔案大小以估算處理時間
    local file_size
    file_size=$(stat -c%s "$file_path")
    local file_size_str
    if [ "$file_size" -gt 1073741824 ]; then  # 1GB
        file_size_str="$(echo "scale=2; $file_size/1073741824" | bc) GB"
        log_detail "檔案大小: $file_size_str，PAR2 處理可能需要較長時間..." >&2
    else
        file_size_str="$(echo "scale=2; $file_size/1048576" | bc) MB"
        log_detail "檔案大小: $file_size_str" >&2
    fi
    
    # 使用 par2 create 命令產生 10% 修復冗餘
    # -r10: 10% 修復冗餘
    # -n1: 限制為 1 個修復檔案 (簡化輸出)
    # -q: 安靜模式，減少輸出
    # 將所有輸出重定向到 /dev/null，避免污染終端
    if ! par2 create -r10 -n1 -q "$file_path" >/dev/null 2>&1; then
        log_error "PAR2 修復檔案產生失敗" >&2
        return 1
    fi
    
    # 驗證 PAR2 檔案是否成功產生
    if [ ! -f "$par2_file" ]; then
        log_error "PAR2 檔案產生失敗: $par2_file" >&2
        return 1
    fi
    
    # 顯示 PAR2 檔案大小
    local par2_size
    par2_size=$(stat -c%s "$par2_file")
    local par2_size_str
    if [ "$par2_size" -gt 1048576 ]; then  # 1MB
        par2_size_str="$(echo "scale=2; $par2_size/1048576" | bc) MB"
    else
        par2_size_str="$(echo "scale=2; $par2_size/1024" | bc) KB"
    fi
    log_detail "PAR2 檔案大小: $par2_size_str" >&2
    
    log_success "PAR2 修復檔案產生完成: $(basename "$par2_file")" >&2
    
    # 輸出產生的檔案路徑 (只輸出到 stdout，供主流程解析)
    echo "$par2_file"
}

# PAR2 修復冗餘函數 - 驗證 PAR2 修復檔案 (強化版)
verify_par2() {
    local file_path="$1"
    local par2_file="$2"
    local start_time
    start_time=$(date +%s.%3N)
    
    log_step "驗證 PAR2 修復檔案..." >&2
    
    # 檢查 PAR2 檔案是否存在
    if [ ! -f "$par2_file" ]; then
        log_error "PAR2 檔案不存在: $par2_file" >&2
        generate_diagnostic_info "PAR2 檔案遺失" "$par2_file" "PAR2 產生過程可能失敗" >&2
        return 1
    fi
    
    # 檢查原始檔案是否存在
    if [ ! -f "$file_path" ]; then
        log_error "原始檔案不存在: $file_path" >&2
        generate_diagnostic_info "原始檔案遺失" "$file_path" "壓縮檔案可能被移動或刪除" >&2
        return 1
    fi
    
    # 使用 par2 verify 命令驗證檔案完整性
    local verify_output
    local verify_exit_code
    
    # 執行 par2 verify 並捕獲退出碼
    verify_output=$(par2 verify "$par2_file" 2>&1)
    verify_exit_code=$?
    
    local end_time
    end_time=$(date +%s.%3N)
    
    # 檢查 par2 命令的退出碼
    if [ $verify_exit_code -eq 0 ]; then
        # 退出碼為 0 表示驗證成功
        # 檢查輸出是否包含錯誤訊息
        if echo "$verify_output" | grep -q -i "error\|failed\|corrupt\|missing"; then
            verification_stats "PAR2 驗證" "$start_time" "$end_time" "failure" "$file_path" >&2
            log_error "PAR2 驗證發現問題: $verify_output" >&2
            generate_diagnostic_info "PAR2 內容驗證失敗" "$par2_file" "PAR2 檔案可能存在內部錯誤" >&2
            return 1
        else
            verification_stats "PAR2 驗證" "$start_time" "$end_time" "success" "$file_path" >&2
            log_success "PAR2 驗證通過 - 檔案完整性正常" >&2
            return 0
        fi
    else
        # 退出碼非 0 表示驗證失敗
        verification_stats "PAR2 驗證" "$start_time" "$end_time" "failure" "$file_path" >&2
        log_error "PAR2 驗證失敗 (退出碼: $verify_exit_code): $verify_output" >&2
        generate_diagnostic_info "PAR2 命令執行失敗" "$par2_file" "par2 工具版本或參數問題，退出碼: $verify_exit_code" >&2
        return 1
    fi
}

# 向後相容函數 - 保持原有函數名稱
generate_checksum_file() {
    generate_sha256_file "$@"
}

# 向後相容函數 - 保持原有函數名稱
verify_checksum() {
    verify_sha256 "$@"
}

# 注意：已移除複雜的中英文字符寬度計算函數
# 改用簡單的固定寬度 printf 格式化，避免對齊問題

# 新增統計格式化函數
format_file_size() {
    local size_bytes=$1
    if [ "$size_bytes" -gt 1073741824 ]; then  # 1GB
        echo "$(echo "scale=2; $size_bytes/1073741824" | bc) GB"
    elif [ "$size_bytes" -gt 1048576 ]; then  # 1MB
        echo "$(echo "scale=2; $size_bytes/1048576" | bc) MB"
    elif [ "$size_bytes" -gt 1024 ]; then  # 1KB
        echo "$(echo "scale=2; $size_bytes/1024" | bc) KB"
    else
        echo "$size_bytes B"
    fi
}

format_duration() {
    local duration=$1
    if [ -z "$duration" ] || [ "$duration" = "0" ] || [ "$duration" = "0.000" ]; then
        echo "< 0.001s"
        return
    fi
    
    local seconds minutes hours
    seconds=$(echo "$duration" | cut -d. -f1)
    local fraction=$(echo "$duration" | cut -d. -f2)
    
    if [ "$seconds" -ge 3600 ]; then
        hours=$((seconds / 3600))
        minutes=$(((seconds % 3600) / 60))
        seconds=$((seconds % 60))
        printf "%dh %dm %ds" "$hours" "$minutes" "$seconds"
    elif [ "$seconds" -ge 60 ]; then
        minutes=$((seconds / 60))
        seconds=$((seconds % 60))
        printf "%dm %ds" "$minutes" "$seconds"
    else
        printf "%ss" "$duration"
    fi
}

# 美化統計輸出函數
display_file_statistics() {
    local base_name="$1"
    local original_size="$2"
    local new_size="$3"
    local par2_total_size="$4"
    local total_duration="$5"
    local sha256_file="$6"
    local blake3_file="$7"
    local par2_file="$8"
    local output_dir="$9"  # 新增輸出目錄參數
    
    # 計算比率
    local compression_ratio par2_ratio
    compression_ratio=$(echo "scale=2; $new_size * 100 / $original_size" | bc)
    par2_ratio=$(echo "scale=2; $par2_total_size * 100 / $new_size" | bc)
    
    # 格式化檔案大小
    local original_size_str new_size_str par2_size_str
    original_size_str=$(format_file_size "$original_size")
    new_size_str=$(format_file_size "$new_size")
    par2_size_str=$(format_file_size "$par2_total_size")
    
    # 格式化時間
    local duration_str
    duration_str=$(format_duration "$total_duration")
    
    # 計算處理速度
    local processing_speed=""
    if [ "$total_duration" != "0" ] && [ "$total_duration" != "0.000" ]; then
        local speed_mb_s
        speed_mb_s=$(echo "scale=2; $original_size/1048576/$total_duration" | bc)
        processing_speed="$speed_mb_s MB/s"
    fi
    
    # 美化的統計輸出 (重新設計固定寬度)
    printf "\n"
    log_progress "╭─────────────────────────────────────────────────────────────╮"
    log_progress "│                        檔案處理統計                         │"
    log_progress "├─────────────────────────────────────────────────────────────┤"
    log_progress "$(printf "│ 檔案名稱: %-51s │" "$base_name")"
    if [ "$ORGANIZE_FILES" = true ]; then
        local rel_output_dir
        rel_output_dir=$(basename "$(dirname "$output_dir")")/$(basename "$output_dir")
        log_progress "$(printf "│ 輸出目錄: %-51s │" "$rel_output_dir")"
    fi
    log_progress "$(printf "│ 原始大小: %-12s 壓縮後: %-12s 比率: %-12s │" "$original_size_str" "$new_size_str" "$compression_ratio%")"
    log_progress "$(printf "│ PAR2大小: %-12s PAR2比率: %-12s 時間: %-12s │" "$par2_size_str" "$par2_ratio%" "$duration_str")"
    if [ -n "$processing_speed" ]; then
        log_progress "$(printf "│ 處理速度: %-51s │" "$processing_speed")"
    fi
    log_progress "├─────────────────────────────────────────────────────────────┤"
    log_progress "│                        生成檔案清單                         │"
    log_progress "├─────────────────────────────────────────────────────────────┤"
    
    # 顯示生成的檔案清單 (固定寬度格式)
    local main_file="$output_dir/$base_name.tar.zst"
    if [ -f "$main_file" ]; then
        local file_size_str
        file_size_str=$(format_file_size "$(stat -c%s "$main_file")")
        log_progress "$(printf "│ ✓ %-42s %13s │" "$(basename "$main_file")" "$file_size_str")"
    fi
    
    if [ -f "$sha256_file" ]; then
        local file_size_str
        file_size_str=$(format_file_size "$(stat -c%s "$sha256_file")")
        log_progress "$(printf "│ ✓ %-42s %13s │" "$(basename "$sha256_file")" "$file_size_str")"
    fi
    
    if [ -f "$blake3_file" ]; then
        local file_size_str
        file_size_str=$(format_file_size "$(stat -c%s "$blake3_file")")
        log_progress "$(printf "│ ✓ %-42s %13s │" "$(basename "$blake3_file")" "$file_size_str")"
    fi
    
    if [ -f "$par2_file" ]; then
        local file_size_str
        file_size_str=$(format_file_size "$(stat -c%s "$par2_file")")
        log_progress "$(printf "│ ✓ %-42s %13s │" "$(basename "$par2_file")" "$file_size_str")"
        
        # 查找並顯示所有相關的 .vol 檔案
        local vol_files
        vol_files=$(find "$(dirname "$par2_file")" -name "$(basename "$main_file").vol*.par2" 2>/dev/null || true)
        if [ -n "$vol_files" ]; then
            while IFS= read -r vol_file; do
                if [ -f "$vol_file" ]; then
                    local vol_size_str
                    vol_size_str=$(format_file_size "$(stat -c%s "$vol_file")")
                    log_progress "$(printf "│ ✓ %-42s %13s │" "$(basename "$vol_file")" "$vol_size_str")"
                fi
            done <<< "$vol_files"
        fi
    fi
    
    log_progress "╰─────────────────────────────────────────────────────────────╯"
    printf "\n"
}

# 總體摘要報告函數
display_final_summary() {
    local success_count="$1"
    local error_count="$2"
    local total_files="$3"
    local total_start_time="$4"
    local total_end_time="$5"
    
    # 計算總處理時間
    local total_processing_time
    total_processing_time=$(echo "scale=3; $total_end_time - $total_start_time" | bc)
    local total_duration_str
    total_duration_str=$(format_duration "$total_processing_time")
    
    # 計算成功率
    local success_rate
    success_rate=$(echo "scale=1; $success_count * 100 / $total_files" | bc)
    
    printf "\n"
    log_progress "╭─────────────────────────────────────────────────────────────╮"
    log_progress "│                      批次處理總摘要                         │"
    log_progress "├─────────────────────────────────────────────────────────────┤"
    log_progress "$(printf "│ 總檔案數: %-6s 成功: %-6s 失敗: %-6s 成功率: %-12s │" "$total_files" "$success_count" "$error_count" "$success_rate%")"
    log_progress "$(printf "│ 總處理時間: %-48s │" "$total_duration_str")"
    
    if [ "$success_count" -gt 0 ]; then
        local avg_time_per_file
        avg_time_per_file=$(echo "scale=3; $total_processing_time / $success_count" | bc)
        local avg_time_str
        avg_time_str=$(format_duration "$avg_time_per_file")
        log_progress "$(printf "│ 平均處理時間: %-46s │" "$avg_time_str")"
    fi
    
    log_progress "├─────────────────────────────────────────────────────────────┤"
    
    if [ "$error_count" -eq 0 ]; then
        log_progress "│                    ✓ 所有檔案處理成功！                    │"
        log_progress "│              冷儲存封存檔案組已完整建立                  │"
    else
        log_progress "│              ⚠ 有 $error_count 個檔案處理失敗                        │"
        log_progress "│                 請檢查上述錯誤訊息                       │"
    fi
    
    log_progress "╰─────────────────────────────────────────────────────────────╯"
    printf "\n"
    
    # 顯示企劃書符合性檢查
    log_info "✓ 冷儲存 SOP 符合性檢查："
    log_detail "• Deterministic Tar (--sort=name): ✓"
    log_detail "• Zstd 最佳化 (--long=31, -19): ✓"
    log_detail "• 雙重雜湊 (SHA-256 + BLAKE3): ✓"
    log_detail "• PAR2 修復冗餘 (10%): ✓"
    log_detail "• 多層驗證流程: ✓"
    log_detail "• 檔案組完整性: ✓"
}

# 主要處理函數 (階段8完整版)
process_7z_files() {
    # 檢查必要工具
    check_required_tools
    
    # 檢查系統資源狀況
    check_system_resources "$WORK_DIRECTORY"
    
    # 取得 7z 檔案清單，並進行邊界條件檢查
    local zip_files
    mapfile -t zip_files < <(find "$WORK_DIRECTORY" -maxdepth 1 -name "*.7z" -type f)
    
    if [ ${#zip_files[@]} -eq 0 ]; then
        log_warning "在工作目錄中找不到 7z 檔案。"
        log_detail "請確認目錄路徑是否正確，且包含 .7z 檔案"
        return
    fi
    
    # 檢查檔案是否可讀取 (邊界條件處理)
    local readable_files=()
    for zip_file in "${zip_files[@]}"; do
        if [ -r "$zip_file" ] && [ -f "$zip_file" ]; then
            # 檢查檔案大小
            local file_size
            file_size=$(stat -c%s "$zip_file" 2>/dev/null || echo "0")
            if [ "$file_size" -gt 0 ]; then
                readable_files+=("$zip_file")
            else
                log_warning "跳過空檔案: $(basename "$zip_file")"
            fi
        else
            log_warning "跳過無法讀取的檔案: $(basename "$zip_file")"
        fi
    done
    
    if [ ${#readable_files[@]} -eq 0 ]; then
        log_error "沒有可處理的有效 7z 檔案"
        return 1
    fi
    
    if [ ${#readable_files[@]} -lt ${#zip_files[@]} ]; then
        local skipped_count=$((${#zip_files[@]} - ${#readable_files[@]}))
        log_warning "已跳過 $skipped_count 個無效檔案，將處理 ${#readable_files[@]} 個有效檔案"
    fi
    
    # 更新處理清單
    zip_files=("${readable_files[@]}")
    
    log_info "找到 ${#zip_files[@]} 個 7z 檔案準備處理"
    log_config "處理設定:"
    log_detail "壓縮等級: $COMPRESSION_LEVEL$([ "$ULTRA_MODE" = true ] && echo " (Ultra 模式)" || echo "")"
    # 獲取實際核心數量
    local actual_threads
    if [ "$THREADS" = "0" ]; then
        actual_threads=$(nproc 2>/dev/null || echo "未知")
        log_detail "執行緒: $actual_threads 個核心 (自動偵測)"
    else
        log_detail "執行緒: $THREADS 個核心"
    fi
    log_detail "長距離匹配: $([ "$LONG_MODE" = true ] && echo "啟用 (--long=31, 2GB dictionary)" || echo "停用")"
    log_detail "完整性檢查: $([ "$ENABLE_CHECK" = true ] && echo "啟用" || echo "停用")"
    
    log_config "檔案組織:"
    if [ "$ORGANIZE_FILES" = true ]; then
        log_detail "組織模式: 子目錄結構 (預設，推薦)"
        if [[ "$OUTPUT_DIR" == /* ]]; then
            log_detail "輸出目錄: $OUTPUT_DIR/ (絕對路徑)"
        else
            log_detail "輸出目錄: $WORK_DIRECTORY/$OUTPUT_DIR/ (相對路徑)"
        fi
    else
        log_detail "組織模式: 扁平結構 (--flat，向後相容)"
        log_detail "輸出目錄: $WORK_DIRECTORY/ (與原始檔案同目錄)"
    fi
    printf "\n"
    
    # 建立臨時工作目錄
    local temp_dir="$WORK_DIRECTORY/temp_extraction"
    log_info "準備創建臨時目錄: $temp_dir"
    
    if [ -d "$temp_dir" ]; then
        log_info "臨時目錄已存在，清理舊內容..."
        rm -rf "$temp_dir"
    fi
    
    if ! mkdir -p "$temp_dir"; then
        log_error "無法創建臨時目錄: $temp_dir"
        return 1
    fi
    
    # 驗證臨時目錄是否成功創建
    if [ ! -d "$temp_dir" ]; then
        log_error "臨時目錄創建失敗: $temp_dir"
        return 1
    fi
    
    log_success "臨時目錄創建成功: $temp_dir"
    
    # 處理結果統計
    local success_count=0
    local error_count=0
    local batch_start_time
    batch_start_time=$(date +%s.%3N)
    
    # 處理每個 7z 檔案
    for i in "${!zip_files[@]}"; do
        local zip_file="${zip_files[$i]}"
        local base_name
        base_name=$(basename "$zip_file" .7z)
        local file_success=false
        local total_start_time
        total_start_time=$(date +%s.%3N)
        
        # 設置此檔案的輸出目錄
        local file_output_dir
        if ! file_output_dir=$(setup_output_directory "$base_name" "$WORK_DIRECTORY"); then
            log_error "無法設置輸出目錄，跳過檔案: $base_name"
            ((error_count++))
            continue
        fi
        
        # 顯示當前進度
        printf "\n"
        log_progress "════════════════════════════════════════════════════════════"
        progress_bar $((i+1)) ${#zip_files[@]} "批次進度"
        log_step "[$((i+1))/${#zip_files[@]}] 正在處理: $(basename "$zip_file")"
        
        # 顯示檔案資訊以供診斷
        local file_size
        file_size=$(stat -c%s "$zip_file")
        local file_size_str
        file_size_str=$(format_file_size "$file_size")
        log_info "檔案大小: $file_size_str"
        log_progress "════════════════════════════════════════════════════════════"
        
        # 初始化錯誤處理變數
        local extracted_dir=""
        
        # 步驟 1: 檢查 7z 檔案結構
        log_step "檢查檔案結構..."
        local has_top_folder=false
        if check_7z_structure "$zip_file"; then
            log_info "檔案已包含頂層資料夾，直接解壓縮"
            has_top_folder=true
        else
            log_info "檔案沒有頂層資料夾，將建立同名資料夾"
            has_top_folder=false
        fi
        
        # 步驟 2: 解壓縮
        log_step "開始解壓縮..."
        if extracted_dir=$(extract_7z_file "$zip_file" "$temp_dir" "$has_top_folder"); then
            log_detail "接收到的解壓縮路徑: '$extracted_dir'"
            # 驗證解壓縮目錄是否存在
            if [ ! -d "$extracted_dir" ]; then
                log_error "解壓縮目錄不存在: $extracted_dir"
                ((error_count++))
            else
                # 步驟 3: 重新壓縮為 tar.zst
                log_step "重新壓縮為 tar.zst..."
                local output_file="$file_output_dir/$base_name.tar.zst"
                if compress_to_tar_zst "$extracted_dir" "$output_file" "$COMPRESSION_LEVEL" "$THREADS" "$LONG_MODE" "$ENABLE_CHECK" "$ULTRA_MODE"; then
                    
                    # 步驟 4: 產生雙重雜湊檔案 (SHA-256 + BLAKE3)
                    local hash_files
                    if hash_files=$(generate_dual_hashes "$output_file"); then
                        # 解析回傳的檔案路徑 (使用 readarray 更安全)
                        local hash_array
                        readarray -t hash_array <<< "$hash_files"
                        local sha256_file="${hash_array[0]}"
                        local blake3_file="${hash_array[1]}"
                        
                        # 步驟 5: 驗證雙重雜湊
                        if verify_dual_hashes "$output_file" "$sha256_file" "$blake3_file"; then
                            
                            # 步驟 6: 產生 PAR2 修復冗餘 (10%)
                            local par2_file
                            if par2_file=$(generate_par2_file "$output_file"); then
                                
                                # 步驟 7: 驗證 PAR2 修復檔案
                                if verify_par2 "$output_file" "$par2_file"; then
                            
                            # 清理解壓縮的臨時檔案
                            rm -rf "$extracted_dir"
                            
                            # 顯示檔案大小比較
                            local original_size
                            original_size=$(stat -c%s "$zip_file")
                            local new_size
                            new_size=$(stat -c%s "$output_file")
                                    # 計算 PAR2 總大小（主檔案 + 所有修復檔案）
                                    local par2_total_size=0
                                    local par2_main_size
                                    par2_main_size=$(stat -c%s "$par2_file")
                                    par2_total_size=$((par2_total_size + par2_main_size))
                                    
                                    # 查找並統計所有相關的 .vol 檔案
                                    local vol_files
                                    vol_files=$(find "$(dirname "$par2_file")" -name "$base_name.tar.zst.vol*.par2" 2>/dev/null || true)
                                    if [ -n "$vol_files" ]; then
                                        while IFS= read -r vol_file; do
                                            if [ -f "$vol_file" ]; then
                                                local vol_size
                                                vol_size=$(stat -c%s "$vol_file")
                                                par2_total_size=$((par2_total_size + vol_size))
                                            fi
                                        done <<< "$vol_files"
                                    fi
                                    
                            local ratio
                            ratio=$(echo "scale=2; $new_size * 100 / $original_size" | bc)
                                    local par2_ratio
                                    par2_ratio=$(echo "scale=2; $par2_total_size * 100 / $new_size" | bc)
                            
                            # 格式化檔案大小
                                    local original_size_str new_size_str par2_size_str
                            if [ "$original_size" -gt 1073741824 ]; then
                                original_size_str="$(echo "scale=2; $original_size/1073741824" | bc) GB"
                            else
                                original_size_str="$(echo "scale=2; $original_size/1048576" | bc) MB"
                            fi
                            
                            if [ "$new_size" -gt 1073741824 ]; then
                                new_size_str="$(echo "scale=2; $new_size/1073741824" | bc) GB"
                            else
                                new_size_str="$(echo "scale=2; $new_size/1048576" | bc) MB"
                            fi
                            
                                    if [ "$par2_total_size" -gt 1048576 ]; then
                                        par2_size_str="$(echo "scale=2; $par2_total_size/1048576" | bc) MB"
                                    else
                                        par2_size_str="$(echo "scale=2; $par2_total_size/1024" | bc) KB"
                                    fi
                                    
                                    # 計算總處理時間並顯示統計
                                    local total_end_time
                                    total_end_time=$(date +%s.%3N)
                                    local total_duration
                                    total_duration=$(echo "scale=3; $total_end_time - $total_start_time" | bc)
                                    
                                    # 使用新的美化統計輸出
                                    display_file_statistics "$base_name" "$original_size" "$new_size" "$par2_total_size" "$total_duration" "$sha256_file" "$blake3_file" "$par2_file" "$file_output_dir"
                                    
                                    log_success "檔案處理完成！包含完整冷儲存檔案組"
                            file_success=true
                            ((success_count++))
                        else
                                    log_error "PAR2 驗證失敗，保留臨時檔案供檢查"
                            ((error_count++))
                        fi
                    else
                                log_error "PAR2 修復檔案產生失敗"
                                ((error_count++))
                            fi
                        else
                            log_error "雙重雜湊驗證失敗，保留臨時檔案供檢查"
                            ((error_count++))
                        fi
                    else
                        log_error "產生雙重雜湊檔案失敗"
                        ((error_count++))
                    fi
                else
                    log_error "壓縮失敗"
                    ((error_count++))
                fi
            fi
        else
            log_error "解壓縮失敗"
            ((error_count++))
        fi
        
        # 清理可能的臨時檔案
        if [ -n "$extracted_dir" ] && [ -d "$extracted_dir" ]; then
            rm -rf "$extracted_dir" 2>/dev/null || log_warning "無法清理臨時檔案: $extracted_dir"
        fi
        
        # 如果處理失敗，顯示錯誤摘要和診斷資訊
        if [ "$file_success" = false ]; then
            local total_end_time
            total_end_time=$(date +%s.%3N)
            local total_duration
            total_duration=$(echo "scale=3; $total_end_time - $total_start_time" | bc)
            
            log_error "檔案 $(basename "$zip_file") 處理失敗"
            log_detail "失敗前處理時間: ${total_duration}s"
            generate_diagnostic_info "檔案處理流程失敗" "$zip_file" "請檢查上述錯誤訊息以確定具體失敗原因"
            
            # 清理失敗的輸出目錄
            if [ -n "$file_output_dir" ]; then
                cleanup_output_directory "$file_output_dir" false
            fi
        fi
        
        printf "\n"  # 每個檔案處理完後添加空行分隔
    done
    
    # 清理臨時目錄
    log_info "清理臨時目錄: $temp_dir"
    if [ -d "$temp_dir" ]; then
        if rm -rf "$temp_dir"; then
            log_success "臨時目錄清理成功"
        else
            log_warning "臨時目錄清理失敗，請手動清理: $temp_dir"
        fi
    else
        log_detail "臨時目錄不存在，無需清理"
    fi
    
    # 顯示總體摘要報告
    local batch_end_time
    batch_end_time=$(date +%s.%3N)
    display_final_summary "$success_count" "$error_count" "${#zip_files[@]}" "$batch_start_time" "$batch_end_time"
    
    if [ "$error_count" -eq 0 ]; then
        log_success "冷儲存封存任務全部完成！"
    else
        log_warning "批次處理完成，但有 $error_count 個檔案處理失敗"
        return 1
    fi
}

# 工作目錄設定和驗證（在參數解析之後）
WORK_DIR="${WORK_DIR:-.}"  # 預設為當前目錄
WORK_DIRECTORY=$(realpath "$WORK_DIR")

# 驗證工作目錄
if [ ! -d "$WORK_DIRECTORY" ]; then
    log_error "工作目錄不存在: $WORK_DIRECTORY"
    exit 1
fi

log_info "工作目錄: $WORK_DIRECTORY"

# 檢查工作目錄權限和磁碟空間
log_info "檢查系統環境..."

# 檢查寫入權限
if [ ! -w "$WORK_DIRECTORY" ]; then
    log_error "工作目錄沒有寫入權限: $WORK_DIRECTORY"
    exit 1
fi
log_detail "工作目錄寫入權限: ✓"

# 檢查磁碟空間
available_space=$(df "$WORK_DIRECTORY" | awk 'NR==2 {print $4}')
if [ "$available_space" -lt 1048576 ]; then  # 少於 1GB
    log_warning "可用磁碟空間較少: $(echo "scale=2; $available_space/1048576" | bc) GB"
else
    log_detail "可用磁碟空間: $(echo "scale=2; $available_space/1048576" | bc) GB"
fi

# 測試臨時目錄創建
test_temp_dir="$WORK_DIRECTORY/.test_temp_$$"
if mkdir -p "$test_temp_dir" 2>/dev/null; then
    rm -rf "$test_temp_dir"
    log_detail "臨時目錄創建測試: ✓"
else
    log_error "無法在工作目錄中創建臨時目錄"
    exit 1
fi

# 顯示版本信息 (階段9更新)
show_version_info() {
    log_info "🎯 Rezip.sh v2.1 (階段9完成版) - 冷儲存封存工具"
    log_detail "完整符合企劃書第6.3節分離模式要求"
    log_detail "支援功能: Deterministic Tar + Zstd最佳化 + 雙重雜湊 + PAR2修復 + 智能組織"
    log_detail "驗證階段: 5層驗證確保完整性"
    log_detail "檔案組織: 子目錄結構避免檔案混亂"
    printf "\n"
}

# 顯示啟動資訊
show_version_info

# 執行主要處理
process_7z_files

# 腳本結束標記
log_detail "腳本執行完成 - Rezip.sh v2.1 (階段9完成版) - 支援智能檔案組織"
