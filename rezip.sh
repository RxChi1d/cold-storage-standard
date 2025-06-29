#!/bin/bash
# Bash Script: 7z 轉 tar.zst 冷儲存轉換工具
# 作者: AI Assistant
# 用途: 將 7z 檔案轉換為 tar.zst 格式以供冷儲存備份
#
# 🎯 Zstd 冷儲存最佳化參數:
# -19: 高壓縮等級，平衡壓縮比和速度
# --long: 長距離匹配，改善重複資料的壓縮效果，使用預設值以提升解壓縮相容性
# --check: 內建完整性檢查，確保資料正確性
#
# 📋 大檔案處理 (>4GB) 及跨平台相容性:
# - 預設使用 POSIX tar 格式，確保跨平台相容性且支援大檔案
# - 備用方案: GNU 格式 (如果 POSIX 不可用)
# - 不支援 ustar 格式 (有 4GB 限制，不適合大檔案處理)

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
  --no-long              停用長距離匹配 (預設會啟用長距離匹配)
  --no-check             停用完整性檢查 (預設會啟用完整性檢查)
  -h, --help             顯示此說明

範例:
  $0                                    # 處理當前目錄的 7z 檔案
  $0 /path/to/7z/files                  # 處理指定目錄的 7z 檔案
  $0 -l 15 -t 4 /path/to/files          # 使用自訂壓縮等級和執行緒數
  $0 -l 22 ~/archives                   # 使用最高壓縮等級 (自動啟用 Ultra 模式)
  $0 --no-long --no-check ~/archives    # 停用長距離匹配和完整性檢查

注意:
  - 需要安裝: 7z, tar (支援 POSIX/GNU 格式), zstd, bc, sha256sum
  - 轉換後的檔案會保存在同一目錄中
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
    local i=0
    
    printf "${COLOR_GRAY}%s " "$message"
    while kill -0 "$pid" 2>/dev/null; do
        printf "\b${spinner:$i:1}"
        i=$(( (i+1) % ${#spinner} ))
        sleep 0.1
    done
    printf "\b "
}

progress_bar() {
    local current=$1
    local total=$2
    local message="$3"
    local width=30
    local percentage=$((current * 100 / total))
    local filled=$((current * width / total))
    local i  # 宣告 i 為 local 變數
    
    # 輸出進度條到新的一行
    printf "${COLOR_BRIGHT_BLUE}%s [" "$message"
    for ((i=0; i<filled; i++)); do printf "█"; done
    for ((i=filled; i<width; i++)); do printf "░"; done
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
    
    # 顯示所有工具檢查結果
    log_success "工具檢查結果:"
    log_detail "7z 狀態: $sevenz_status"
    log_detail "tar 狀態: $tar_status"
    log_detail "zstd 狀態: $zstd_status"
    log_detail "bc 狀態: $bc_status"
    log_detail "sha256sum 狀態: $sha256_status"
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少必要工具: ${missing[*]}。請安裝後重試。"
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

# 檢查 7z 檔案結構
check_7z_structure() {
    local zip_file="$1"
    
    # 使用 7z 列表命令檢查結構
    local list_output
    if ! list_output=$(7z l "$zip_file" -ba 2>/dev/null); then
        log_warning "無法分析壓縮檔結構，將建立資料夾"
        return 1
    fi
    
    if [ -z "$list_output" ]; then
        return 1
    fi
    
    # 檢查所有檔案是否在同一個頂層資料夾中
    local top_level_items=()
    while IFS= read -r line; do
        # 跳過目錄項目並取得檔案路徑
        if [[ $line =~ ^D[[:space:]]+ ]] || [ -z "${line// }" ]; then
            continue
        fi
        
        # 提取檔案路徑 (在檔案屬性之後)
        if [[ $line =~ ^[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+(.+)$ ]]; then
            local file_name="${BASH_REMATCH[1]// /}"
            if [ -n "$file_name" ]; then
                local top_level
                top_level=$(echo "$file_name" | cut -d'/' -f1 | cut -d'\' -f1)
                if [[ ! " ${top_level_items[*]} " =~ " $top_level " ]]; then
                    top_level_items+=("$top_level")
                fi
            fi
        fi
    done <<< "$list_output"
    
    # 如果只有一個頂層項目且為資料夾則回傳 true
    [ ${#top_level_items[@]} -eq 1 ]
}

# 解壓縮 7z 檔案
extract_7z_file() {
    local zip_file="$1"
    local output_dir="$2"
    local create_folder="$3"
    
    local base_name
    base_name=$(basename "$zip_file" .7z)
    
    # 驗證輸出目錄是否存在
    if [ ! -d "$output_dir" ]; then
        log_error "輸出目錄不存在: $output_dir"
        return 1
    fi
    
    # 將除錯訊息輸出到 stderr，避免混入返回值
    log_detail "解壓縮參數: 檔案=$zip_file, 輸出目錄=$output_dir, 創建資料夾=$create_folder" >&2
    
    if [ "$create_folder" = true ]; then
        # 需要建立同名資料夾
        local target_dir="$output_dir/$base_name"
        log_detail "準備創建目標目錄: $target_dir" >&2
        
        if ! mkdir -p "$target_dir"; then
            log_error "無法創建目標目錄: $target_dir"
            return 1
        fi
        
        # 驗證目標目錄是否成功創建
        if [ ! -d "$target_dir" ]; then
            log_error "目標目錄創建失敗: $target_dir"
            return 1
        fi
        
        log_detail "目標目錄創建成功: $target_dir" >&2
        
        # 解壓縮到目標目錄
        log_detail "開始解壓縮到: $target_dir" >&2
        if ! 7z x "$zip_file" -o"$target_dir" -y >/dev/null 2>&1; then
            log_error "7z 解壓縮失敗"
            # 清理失敗的目錄
            rm -rf "$target_dir" 2>/dev/null
            return 1
        fi
        
        # 驗證解壓縮結果
        if [ ! -d "$target_dir" ] || [ -z "$(ls -A "$target_dir" 2>/dev/null)" ]; then
            log_error "解壓縮後目錄為空或不存在: $target_dir"
            return 1
        fi
        
        # 先輸出路徑，再顯示成功訊息
        echo "$target_dir"
        log_success "已解壓縮至: $target_dir" >&2
    else
        # 直接解壓縮到輸出目錄
        log_detail "開始解壓縮到: $output_dir" >&2
        if ! 7z x "$zip_file" -o"$output_dir" -y >/dev/null 2>&1; then
            log_error "7z 解壓縮失敗"
            return 1
        fi
        
        # 尋找解壓縮的資料夾
        local extracted_dir="$output_dir/$base_name"
        if [ ! -d "$extracted_dir" ]; then
            # 如果預期的資料夾不存在，尋找實際解壓縮的內容
            log_detail "預期目錄不存在，搜尋實際解壓縮內容..." >&2
            local found_dirs
            found_dirs=$(find "$output_dir" -maxdepth 1 -type d -name "*$base_name*" | head -1)
            if [ -n "$found_dirs" ]; then
                extracted_dir="$found_dirs"
                log_detail "找到解壓縮目錄: $extracted_dir" >&2
            else
                log_error "在 $output_dir 中找不到解壓縮目錄"
                # 列出輸出目錄內容以供除錯
                log_detail "輸出目錄內容:" >&2
                ls -la "$output_dir" | while read line; do
                    log_detail "  $line" >&2
                done
                return 1
            fi
        fi
        
        # 驗證解壓縮結果
        if [ ! -d "$extracted_dir" ] || [ -z "$(ls -A "$extracted_dir" 2>/dev/null)" ]; then
            log_error "解壓縮後目錄為空或不存在: $extracted_dir"
            return 1
        fi
        
        # 先輸出路徑，再顯示成功訊息
        echo "$extracted_dir"
        log_success "已解壓縮至: $extracted_dir" >&2
    fi
}

# 重新壓縮為 tar.zst
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
    
    local temp_tar="${output_file%.zst}"
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
    
    # 長距離匹配
    if [ "$long_mode" = true ]; then
        zstd_params+=("--long")
    fi
    
    # 完整性檢查
    if [ "$enable_check" = true ]; then
        zstd_params+=("--check")
    fi
    
    # 強制覆蓋已存在的檔案
    zstd_params+=("--force")
    
    log_detail "zstd 參數: ${zstd_params[*]}"
    
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
    
    # 切換到輸入目錄的父目錄
    local current_dir=$(pwd)
    local parent_dir=$(dirname "$input_dir")
    local folder_name=$(basename "$input_dir")
    
    cd "$parent_dir" || return 1
    
    # 執行壓縮 (使用 POSIX 或 GNU 格式)
    if ! tar --format="$best_format" -cf - "$folder_name" | zstd "${zstd_params[@]}" > "$output_file"; then
        log_error "壓縮失敗"
        cd "$current_dir"
        return 1
    fi
    
    cd "$current_dir"
    log_success "已壓縮至: $output_file"
}

# 產生 SHA256 校驗和檔案
generate_checksum_file() {
    local file_path="$1"
    
    local hash
    hash=$(sha256sum "$file_path" | cut -d' ' -f1)
    local checksum_file="$file_path.sha256"
    local file_name
    file_name=$(basename "$file_path")
    
    echo "$hash  $file_name" > "$checksum_file"
    
    # 先輸出路徑，再顯示成功訊息（重定向到 stderr）
    echo "$checksum_file"
    log_success "校驗和檔案已產生: $checksum_file" >&2
}

# 驗證校驗和檔案
verify_checksum() {
    local file_path="$1"
    local checksum_file="$2"
    
    local expected_hash
    expected_hash=$(cut -d' ' -f1 "$checksum_file")
    local actual_hash
    actual_hash=$(sha256sum "$file_path" | cut -d' ' -f1)
    
    if [ "$expected_hash" = "$actual_hash" ]; then
        log_success "校驗和驗證通過"
        return 0
    else
        log_error "校驗和驗證失敗！預期: $expected_hash，實際: $actual_hash"
        return 1
    fi
}

# 主要處理函數
process_7z_files() {
    # 檢查必要工具
    check_required_tools
    
    # 取得 7z 檔案清單
    local zip_files
    mapfile -t zip_files < <(find "$WORK_DIRECTORY" -maxdepth 1 -name "*.7z" -type f)
    
    if [ ${#zip_files[@]} -eq 0 ]; then
        log_warning "在工作目錄中找不到 7z 檔案。"
        return
    fi
    
    log_info "找到 ${#zip_files[@]} 個 7z 檔案準備處理"
    log_config "壓縮設定:"
    log_detail "等級: $COMPRESSION_LEVEL$([ "$ULTRA_MODE" = true ] && echo " (Ultra 模式)" || echo "")"
    # 獲取實際核心數量
    local actual_threads
    if [ "$THREADS" = "0" ]; then
        actual_threads=$(nproc 2>/dev/null || echo "未知")
        log_detail "執行緒: $actual_threads 個核心 (自動偵測)"
    else
        log_detail "執行緒: $THREADS 個核心"
    fi
    log_detail "長距離匹配: $([ "$LONG_MODE" = true ] && echo "啟用" || echo "停用")"
    log_detail "完整性檢查: $([ "$ENABLE_CHECK" = true ] && echo "啟用" || echo "停用")"
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
    
    # 處理每個 7z 檔案
    for i in "${!zip_files[@]}"; do
        local zip_file="${zip_files[$i]}"
        local base_name
        base_name=$(basename "$zip_file" .7z)
        local file_success=false
        
        # 顯示當前進度
        progress_bar $((i+1)) ${#zip_files[@]} "處理進度"
        log_step "[$((i+1))/${#zip_files[@]}] 處理檔案: $(basename "$zip_file")"
        
        # 顯示檔案資訊以供診斷
        local file_size
        file_size=$(stat -c%s "$zip_file")
        local file_size_str
        if [ "$file_size" -gt 1073741824 ]; then  # 1GB
            file_size_str="$(echo "scale=2; $file_size/1073741824" | bc) GB"
        else
            file_size_str="$(echo "scale=2; $file_size/1048576" | bc) MB"
        fi
        log_info "檔案大小: $file_size_str"
        
        # 初始化錯誤處理變數
        local extracted_dir=""
        
        # 步驟 1: 檢查 7z 檔案結構
        log_step "檢查檔案結構..."
        local need_create_folder=true
        if check_7z_structure "$zip_file"; then
            log_info "檔案已包含頂層資料夾，直接解壓縮"
            need_create_folder=false
        else
            log_info "檔案沒有頂層資料夾，將建立同名資料夾"
            need_create_folder=true
        fi
        
        # 步驟 2: 解壓縮
        log_step "開始解壓縮..."
        if extracted_dir=$(extract_7z_file "$zip_file" "$temp_dir" "$need_create_folder"); then
            log_detail "接收到的解壓縮路徑: '$extracted_dir'"
            # 驗證解壓縮目錄是否存在
            if [ ! -d "$extracted_dir" ]; then
                log_error "解壓縮目錄不存在: $extracted_dir"
                ((error_count++))
            else
                # 步驟 3: 重新壓縮為 tar.zst
                log_step "重新壓縮為 tar.zst..."
                local output_file="$WORK_DIRECTORY/$base_name.tar.zst"
                if compress_to_tar_zst "$extracted_dir" "$output_file" "$COMPRESSION_LEVEL" "$THREADS" "$LONG_MODE" "$ENABLE_CHECK" "$ULTRA_MODE"; then
                    
                    # 步驟 4: 產生校驗和檔案
                    log_step "產生校驗和檔案..."
                    local checksum_file
                    if checksum_file=$(generate_checksum_file "$output_file"); then
                        
                        # 步驟 5: 驗證校驗和檔案
                        log_step "驗證校驗和檔案..."
                        if verify_checksum "$output_file" "$checksum_file"; then
                            
                            # 清理解壓縮的臨時檔案
                            rm -rf "$extracted_dir"
                            
                            # 顯示檔案大小比較
                            local original_size
                            original_size=$(stat -c%s "$zip_file")
                            local new_size
                            new_size=$(stat -c%s "$output_file")
                            local ratio
                            ratio=$(echo "scale=2; $new_size * 100 / $original_size" | bc)
                            
                            # 格式化檔案大小
                            local original_size_str new_size_str
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
                            
                            log_progress "原始檔案: $original_size_str"
                            log_progress "新檔案: $new_size_str (壓縮比: $ratio%)"
                            log_success "檔案處理完成！"
                            file_success=true
                            ((success_count++))
                        else
                            log_error "校驗和失敗，保留臨時檔案供檢查"
                            ((error_count++))
                        fi
                    else
                        log_error "產生校驗和檔案失敗"
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
        
        # 如果處理失敗，顯示錯誤摘要
        if [ "$file_success" = false ]; then
            log_error "檔案 $(basename "$zip_file") 處理失敗"
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
    
    # 顯示處理結果摘要
    log_info "處理結果摘要:"
    log_detail "成功: $success_count 個檔案"
    log_detail "失敗: $error_count 個檔案"
    
    if [ "$error_count" -eq 0 ]; then
        log_success "所有檔案處理完成！"
    else
        log_warning "處理完成，但有 $error_count 個檔案失敗"
        return 1
    fi
}

# 工作目錄設定和驗證（在參數解析之後）
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

# 執行主要處理
process_7z_files
