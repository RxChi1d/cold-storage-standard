#!/bin/bash
# 解壓縮腳本 - 冷儲存封存檔案解壓縮工具
# 作者: AI Assistant
# 版本: v2.0
# 用途: 專門負責 tar.zst 檔案的解壓縮
#
# [EXTRACT] 解壓縮流程：
# 1. 安全的目標目錄創建
# 2. 檔案覆蓋保護機制
# 3. 使用正確的 zstd 參數進行解壓縮
# 4. 解壓縮進度和統計資訊
# 5. 解壓縮後基本驗證
#
# [USAGE] 使用方式:
# ./extract-archive.sh file.tar.zst                    # 解壓縮到當前目錄
# ./extract-archive.sh -o /path/to/output file.tar.zst # 指定輸出目錄
# ./extract-archive.sh -f file.tar.zst                 # 強制覆蓋現有檔案

# 顯示使用說明
show_usage() {
    cat << EOF
使用方法: $0 [選項] <檔案路徑>

參數:
  檔案路徑                tar.zst 檔案路徑

選項:
  -o, --output DIR        指定解壓縮輸出目錄 (預設: 檔案名稱目錄)
  -f, --force            強制覆蓋現有檔案
  -v, --verbose          顯示詳細解壓縮資訊
  -q, --quiet            安靜模式，減少輸出
  -h, --help             顯示此說明

解壓縮流程:
  1. 目標目錄準備
  2. 兩階段解壓縮 (zstd 解壓縮 → tar 展開)
  3. 解壓縮後基本驗證
  4. 統計資訊報告

安全特性:
  + 覆蓋保護機制
  + 目標目錄安全創建
  + 解壓縮進度顯示
  + 詳細錯誤報告

範例:
  $0 archive.tar.zst                        # 解壓縮到 ./archive/
  $0 -o /tmp/extract archive.tar.zst        # 指定輸出目錄
  $0 -f archive.tar.zst                     # 強制覆蓋模式
  $0 -v archive.tar.zst                     # 詳細模式

注意事項:
  此腳本僅負責解壓縮，不進行完整性驗證
  建議使用前先執行 verify-archive.sh 驗證檔案完整性
  或使用 verify-and-extract.sh 進行完整的驗證與解壓縮流程

[SYSTEM] 系統需求:
  工具依賴: zstd, tar
  相容性: 與 archive-compress.sh v2.1 完全相容
EOF
}

# 預設參數
VERBOSE=false
QUIET=false
FORCE_OVERWRITE=false
OUTPUT_DIR=""
TARGET_FILE=""

# 顏色定義
declare -r COLOR_RED='\033[0;31m'
declare -r COLOR_GREEN='\033[0;32m'
declare -r COLOR_YELLOW='\033[0;33m'
declare -r COLOR_BLUE='\033[0;34m'
declare -r COLOR_CYAN='\033[0;36m'
declare -r COLOR_GRAY='\033[0;90m'
declare -r COLOR_RESET='\033[0m'

# 日誌函數
log_info() {
    if [ "$QUIET" = false ]; then
        printf "${COLOR_CYAN}* %s${COLOR_RESET}\n" "$1"
    fi
}

log_success() {
    printf "${COLOR_GREEN}+ %s${COLOR_RESET}\n" "$1"
}

log_warning() {
    printf "${COLOR_YELLOW}! %s${COLOR_RESET}\n" "$1"
}

log_error() {
    printf "${COLOR_RED}- %s${COLOR_RESET}\n" "$1" >&2
}

log_detail() {
    if [ "$VERBOSE" = true ] && [ "$QUIET" = false ]; then
        printf "${COLOR_GRAY}  %s${COLOR_RESET}\n" "$1"
    fi
}

log_step() {
    if [ "$QUIET" = false ]; then
        printf "${COLOR_BLUE}~ %s${COLOR_RESET}\n" "$1"
    fi
}

# 解析命令列參數
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -o|--output)
                shift
                if [[ -n "$1" ]]; then
                    OUTPUT_DIR="$1"
                    shift
                else
                    log_error "錯誤: --output 需要指定目錄路徑"
                    exit 1
                fi
                ;;
            -f|--force)
                FORCE_OVERWRITE=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                log_error "錯誤: 未知選項 $1"
                echo "使用 $0 --help 查看使用說明" >&2
                exit 1
                ;;
            *)
                # 這是檔案路徑
                if [[ -z "$TARGET_FILE" ]]; then
                    TARGET_FILE="$1"
                else
                    log_error "錯誤: 只能指定一個檔案"
                    exit 1
                fi
                shift
                ;;
        esac
    done
}

# 檢查必要工具
check_required_tools() {
    local missing=()
    
    # 只檢查解壓縮必需的工具
    for tool in zstd tar; do
        if ! command -v "$tool" &> /dev/null; then
            missing+=("$tool")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少必要工具: ${missing[*]}"
        log_info ""
        log_info "安裝建議 (Ubuntu/Debian):"
        log_info "sudo apt update && apt install zstd"
        exit 1
    fi
    
    log_detail "所有必要工具已安裝"
}

# 格式化檔案大小
format_size() {
    local bytes="$1"
    if [ "$bytes" -ge 1073741824 ]; then
        echo "$(echo "scale=1; $bytes/1073741824" | bc)GB"
    elif [ "$bytes" -ge 1048576 ]; then
        echo "$(echo "scale=1; $bytes/1048576" | bc)MB"
    elif [ "$bytes" -ge 1024 ]; then
        echo "$(echo "scale=1; $bytes/1024" | bc)KB"
    else
        echo "${bytes}B"
    fi
}

# 顯示分隔線
print_separator() {
    if [ "$QUIET" = false ]; then
        printf "%*s\n" 60 "" | tr ' ' '='
    fi
}

# 準備輸出目錄
prepare_output_directory() {
    local file_path="$1"
    local file_basename
    
    # 計算預設輸出目錄
    if [ -z "$OUTPUT_DIR" ]; then
        file_basename=$(basename "$file_path" .tar.zst)
        OUTPUT_DIR="./$file_basename"
    fi
    
    log_step "準備輸出目錄: $OUTPUT_DIR"
    
    # 檢查目錄是否已存在
    if [ -d "$OUTPUT_DIR" ]; then
        if [ "$FORCE_OVERWRITE" = false ]; then
            # 檢查目錄是否為空
            if [ "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]; then
                log_error "輸出目錄已存在且不為空: $OUTPUT_DIR"
                log_info "使用 --force 選項強制覆蓋，或指定其他目錄"
                return 1
            else
                log_detail "輸出目錄已存在但為空"
            fi
        else
            log_warning "強制覆蓋模式：清理現有目錄"
            if ! rm -rf "$OUTPUT_DIR"/*; then
                log_error "無法清理現有目錄: $OUTPUT_DIR"
                return 1
            fi
        fi
    else
        # 創建目錄
        log_detail "創建輸出目錄"
        if ! mkdir -p "$OUTPUT_DIR"; then
            log_error "無法創建輸出目錄: $OUTPUT_DIR"
            return 1
        fi
    fi
    
    # 檢查目錄權限
    if [ ! -w "$OUTPUT_DIR" ]; then
        log_error "輸出目錄沒有寫入權限: $OUTPUT_DIR"
        return 1
    fi
    
    log_success "輸出目錄準備完成: $OUTPUT_DIR"
    return 0
}

# 執行解壓縮
perform_extraction() {
    local file_path="$1"
    local file_basename
    file_basename=$(basename "$file_path")
    
    log_step "開始解壓縮: $file_basename"
    
    # 取得檔案大小用於進度估算
    local file_size
    if [ -f "$file_path" ]; then
        file_size=$(stat -c%s "$file_path")
        log_detail "壓縮檔案大小: $(format_size "$file_size")"
    fi
    
    # 記錄開始時間
    local start_time
    start_time=$(date +%s.%3N)
    
    # 執行解壓縮（zstd 解壓縮 + tar 解開）
    log_detail "執行解壓縮命令: zstd -dc --long=31 | tar -xf -"
    
    if [ "$VERBOSE" = true ]; then
        # 詳細模式：顯示檔案列表
        log_detail "解壓縮檔案到: $OUTPUT_DIR"
        if zstd -dc --long=31 "$file_path" | tar -xvf - -C "$OUTPUT_DIR"; then
            local end_time duration
            end_time=$(date +%s.%3N)
            duration=$(echo "scale=2; $end_time - $start_time" | bc)
            log_success "解壓縮完成 (zstd + tar) (耗時: ${duration}s)"
        else
            log_error "解壓縮失敗"
            return 1
        fi
    else
        # 正常模式：安靜解壓縮
        log_detail "解壓縮檔案到: $OUTPUT_DIR"
        if zstd -dc --long=31 "$file_path" | tar -xf - -C "$OUTPUT_DIR"; then
            local end_time duration
            end_time=$(date +%s.%3N)
            duration=$(echo "scale=2; $end_time - $start_time" | bc)
            log_success "解壓縮完成 (zstd + tar) (耗時: ${duration}s)"
        else
            log_error "解壓縮失敗"
            return 1
        fi
    fi
    
    return 0
}

# 解壓縮後基本驗證
post_extraction_verification() {
    local output_dir="$1"
    
    log_step "執行解壓縮後基本驗證..."
    
    # 檢查輸出目錄
    if [ ! -d "$output_dir" ]; then
        log_error "輸出目錄不存在: $output_dir"
        return 1
    fi
    
    # 計算解壓縮後的檔案統計
    local file_count total_size
    file_count=$(find "$output_dir" -type f | wc -l)
    total_size=$(find "$output_dir" -type f -exec stat -c%s {} + | awk '{sum+=$1} END {print sum}')
    
    if [ "$file_count" -eq 0 ]; then
        log_error "解壓縮後沒有檔案"
        return 1
    fi
    
    log_success "基本驗證通過"
    log_detail "檔案數量: $file_count"
    log_detail "總計大小: $(format_size "$total_size")"
    
    # 如果在詳細模式，顯示目錄結構概覽
    if [ "$VERBOSE" = true ]; then
        log_detail "目錄結構概覽:"
        find "$output_dir" -type d | head -10 | while read -r dir; do
            log_detail "  目錄: $(basename "$dir")"
        done
        if [ "$(find "$output_dir" -type d | wc -l)" -gt 10 ]; then
            log_detail "  ... (更多目錄)"
        fi
    fi
    
    return 0
}

# 顯示解壓縮統計
show_extraction_stats() {
    local file_path="$1"
    local output_dir="$2"
    local start_time="$3"
    local end_time
    end_time=$(date +%s.%3N)
    
    if [ "$QUIET" = false ]; then
        print_separator
        log_info "解壓縮統計報告"
        print_separator
        
        # 檔案資訊
        log_info "來源檔案: $(basename "$file_path")"
        log_info "輸出目錄: $output_dir"
        
        # 大小資訊
        if [ -f "$file_path" ]; then
            local compressed_size
            compressed_size=$(stat -c%s "$file_path")
            log_info "壓縮大小: $(format_size "$compressed_size")"
        fi
        
        if [ -d "$output_dir" ]; then
            local extracted_size file_count
            extracted_size=$(find "$output_dir" -type f -exec stat -c%s {} + | awk '{sum+=$1} END {print sum}')
            file_count=$(find "$output_dir" -type f | wc -l)
            log_info "解壓大小: $(format_size "$extracted_size")"
            log_info "檔案數量: $file_count"
            
            # 計算壓縮比
            if [ -f "$file_path" ] && [ "$extracted_size" -gt 0 ]; then
                local compression_ratio
                compression_ratio=$(echo "scale=1; ($compressed_size * 100) / $extracted_size" | bc)
                log_info "壓縮比率: ${compression_ratio}%"
            fi
        fi
        
        # 時間資訊
        local total_time
        total_time=$(echo "scale=2; $end_time - $start_time" | bc)
        log_info "總計時間: ${total_time}s"
        
        print_separator
    fi
}

# 驗證輸入參數
validate_input() {
    # 檢查是否提供了檔案路徑
    if [ -z "$TARGET_FILE" ]; then
        log_error "錯誤: 需要指定要解壓縮的檔案"
        echo "使用 $0 --help 查看使用說明" >&2
        exit 1
    fi
    
    # 檢查檔案是否存在
    if [ ! -f "$TARGET_FILE" ]; then
        log_error "錯誤: 檔案不存在: $TARGET_FILE"
        exit 1
    fi
    
    # 檢查檔案副檔名
    if [[ ! "$TARGET_FILE" =~ \.tar\.zst$ ]]; then
        log_error "錯誤: 只支援 .tar.zst 檔案"
        exit 1
    fi
    
    # 轉換為絕對路徑
    TARGET_FILE=$(realpath "$TARGET_FILE")
    
    log_detail "目標檔案: $TARGET_FILE"
}

# 主要處理函數
main() {
    local start_time
    start_time=$(date +%s.%3N)
    
    # 解析參數
    parse_arguments "$@"
    
    # 驗證輸入
    validate_input
    
    # 檢查必要工具
    check_required_tools
    
    # 顯示開始資訊
    if [ "$QUIET" = false ]; then
        log_info "解壓縮工具 v2.0 - 專門的 tar.zst 解壓縮工具"
        log_info "檔案: $(basename "$TARGET_FILE")"
        log_warning "注意: 此工具不進行完整性驗證，建議先使用 verify-archive.sh"
        echo
    fi
    
    # 準備輸出目錄
    if ! prepare_output_directory "$TARGET_FILE"; then
        exit 1
    fi
    echo
    
    # 執行解壓縮
    if ! perform_extraction "$TARGET_FILE"; then
        log_error "解壓縮失敗"
        exit 1
    fi
    echo
    
    # 解壓縮後基本驗證
    if ! post_extraction_verification "$OUTPUT_DIR"; then
        log_error "解壓縮後基本驗證失敗"
        exit 1
    fi
    echo
    
    # 顯示統計報告
    show_extraction_stats "$TARGET_FILE" "$OUTPUT_DIR" "$start_time"
    
    # 成功完成
    log_success "解壓縮完成！檔案已解壓縮到: $OUTPUT_DIR"
    exit 0
}

# 執行主函數
main "$@" 