#!/bin/bash
# 驗證與解壓縮腳本 - 冷儲存封存檔案安全處理工具
# 作者: AI Assistant
# 版本: v1.0
# 用途: 先完整驗證再安全解壓縮 tar.zst 檔案
#
# [WORKFLOW] 工作流程：
# 1. 使用 verify-archive.sh 進行完整性驗證
# 2. 驗證通過後使用 extract-archive.sh 進行解壓縮
# 3. 提供統一的參數接口和清晰的進度報告
# 4. 完整的錯誤處理和統計資訊
#
# [USAGE] 使用方式:
# ./verify-and-extract.sh file.tar.zst                    # 驗證並解壓縮到預設目錄
# ./verify-and-extract.sh -o /path/to/output file.tar.zst # 指定輸出目錄
# ./verify-and-extract.sh -f file.tar.zst                 # 強制覆蓋模式

# 顯示使用說明
show_usage() {
    cat << EOF
使用方法: $0 [選項] <檔案路徑>

參數:
  檔案路徑                tar.zst 檔案路徑

選項:
  -o, --output DIR        指定解壓縮輸出目錄 (預設: 檔案名稱目錄)
  -f, --force            強制覆蓋現有檔案
  -v, --verbose          顯示詳細資訊
  -q, --quiet            安靜模式，減少輸出
  --verify-only          僅執行驗證，不解壓縮
  --skip-verify          跳過驗證直接解壓縮 (不建議)
  -h, --help             顯示此說明

工作流程:
  第一階段: 完整性驗證
    + zstd 檔案完整性檢查
    + SHA-256 雜湊驗證
    + BLAKE3 雜湊驗證
    + PAR2 冗餘完整性檢查
    + tar 內容結構驗證
  
  第二階段: 安全解壓縮
    + 目標目錄準備
    + 兩階段解壓縮 (zstd + tar)
    + 解壓縮後驗證
    + 統計資訊報告

安全特性:
  + 強制完整性驗證 (可選跳過)
  + 覆蓋保護機制
  + 詳細錯誤報告
  + 完整統計資訊

範例:
  $0 archive.tar.zst                        # 標準驗證與解壓縮
  $0 -o /tmp/extract archive.tar.zst        # 指定輸出目錄
  $0 -f archive.tar.zst                     # 強制覆蓋模式
  $0 -v archive.tar.zst                     # 詳細模式
  $0 --verify-only archive.tar.zst          # 僅執行驗證
  $0 --skip-verify archive.tar.zst          # 跳過驗證 (不建議)

[SYSTEM] 系統需求:
  腳本依賴: verify-archive.sh v1.0, extract-archive.sh v2.0
  工具依賴: zstd, tar, sha256sum, b3sum, par2
EOF
}

# 預設參數
VERBOSE=false
QUIET=false
FORCE_OVERWRITE=false
VERIFY_ONLY=false
SKIP_VERIFY=false
OUTPUT_DIR=""
TARGET_FILE=""

# 顏色定義
declare -r COLOR_RED='\033[0;31m'
declare -r COLOR_GREEN='\033[0;32m'
declare -r COLOR_YELLOW='\033[0;33m'
declare -r COLOR_BLUE='\033[0;34m'
declare -r COLOR_CYAN='\033[0;36m'
declare -r COLOR_MAGENTA='\033[0;35m'
declare -r COLOR_GRAY='\033[0;90m'
declare -r COLOR_RESET='\033[0m'

# 日誌函數
log_info() {
    if [ "$QUIET" = false ]; then
        printf "${COLOR_CYAN}* %s${COLOR_RESET}\n" "$1"
    fi
}

log_success() {
    printf "${COLOR_GREEN}✓ %s${COLOR_RESET}\n" "$1"
}

log_warning() {
    printf "${COLOR_YELLOW}⚠ %s${COLOR_RESET}\n" "$1"
}

log_error() {
    printf "${COLOR_RED}✗ %s${COLOR_RESET}\n" "$1" >&2
}

log_detail() {
    if [ "$VERBOSE" = true ] && [ "$QUIET" = false ]; then
        printf "${COLOR_GRAY}  %s${COLOR_RESET}\n" "$1"
    fi
}

log_step() {
    if [ "$QUIET" = false ]; then
        printf "${COLOR_BLUE}▶ %s${COLOR_RESET}\n" "$1"
    fi
}

log_phase() {
    if [ "$QUIET" = false ]; then
        printf "${COLOR_MAGENTA}═══ %s ═══${COLOR_RESET}\n" "$1"
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
            --verify-only)
                VERIFY_ONLY=true
                shift
                ;;
            --skip-verify)
                SKIP_VERIFY=true
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

# 檢查腳本依賴
check_script_dependencies() {
    local missing=()
    local script_dir
    script_dir="$(dirname "$0")"
    
    # 檢查 verify-archive.sh
    if [ ! -f "$script_dir/verify-archive.sh" ] && [ ! -f "./verify-archive.sh" ]; then
        missing+=("verify-archive.sh")
    fi
    
    # 檢查 extract-archive.sh (僅在需要解壓縮時)
    if [ "$VERIFY_ONLY" = false ]; then
        if [ ! -f "$script_dir/extract-archive.sh" ] && [ ! -f "./extract-archive.sh" ]; then
            missing+=("extract-archive.sh")
        fi
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少必要腳本: ${missing[*]}"
        log_info ""
        log_info "請確保以下腳本在同一目錄中："
        log_info "- verify-archive.sh"
        if [ "$VERIFY_ONLY" = false ]; then
            log_info "- extract-archive.sh"
        fi
        exit 1
    fi
    
    log_detail "所有必要腳本已找到"
}

# 尋找腳本路徑
find_script() {
    local script_name="$1"
    local script_dir
    script_dir="$(dirname "$0")"
    
    # 優先檢查腳本所在目錄
    if [ -f "$script_dir/$script_name" ]; then
        echo "$script_dir/$script_name"
    elif [ -f "./$script_name" ]; then
        echo "./$script_name"
    else
        return 1
    fi
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
        printf "%*s\n" 70 "" | tr ' ' '═'
    fi
}

# 顯示檔案資訊
show_file_info() {
    local file_path="$1"
    
    if [ "$QUIET" = false ]; then
        print_separator
        log_info "檔案資訊"
        print_separator
        log_info "檔案名稱: $(basename "$file_path")"
        log_info "檔案路徑: $file_path"
        
        if [ -f "$file_path" ]; then
            local file_size
            file_size=$(stat -c%s "$file_path")
            log_info "檔案大小: $(format_size "$file_size")"
        fi
        
        print_separator
        echo
    fi
}

# 執行驗證階段
execute_verification() {
    local file_path="$1"
    local verify_script
    
    log_phase "第一階段: 完整性驗證"
    echo
    
    verify_script=$(find_script "verify-archive.sh")
    if [ $? -ne 0 ]; then
        log_error "找不到 verify-archive.sh 腳本"
        return 1
    fi
    
    log_step "使用 verify-archive.sh 執行完整驗證..."
    log_detail "腳本路徑: $verify_script"
    
    # 建構驗證命令參數
    local verify_args=()
    if [ "$VERBOSE" = true ]; then
        verify_args+=("-v")
    elif [ "$QUIET" = true ]; then
        verify_args+=("-q")
    fi
    verify_args+=("$file_path")
    
    # 執行驗證
    local start_time end_time duration
    start_time=$(date +%s.%3N)
    
    if bash "$verify_script" "${verify_args[@]}"; then
        end_time=$(date +%s.%3N)
        duration=$(echo "scale=2; $end_time - $start_time" | bc)
        echo
        log_success "驗證階段完成 (耗時: ${duration}s)"
        return 0
    else
        end_time=$(date +%s.%3N)
        duration=$(echo "scale=2; $end_time - $start_time" | bc)
        echo
        log_error "驗證階段失敗 (耗時: ${duration}s)"
        return 1
    fi
}

# 執行解壓縮階段
execute_extraction() {
    local file_path="$1"
    local extract_script
    
    echo
    log_phase "第二階段: 安全解壓縮"
    echo
    
    extract_script=$(find_script "extract-archive.sh")
    if [ $? -ne 0 ]; then
        log_error "找不到 extract-archive.sh 腳本"
        return 1
    fi
    
    log_step "使用 extract-archive.sh 執行解壓縮..."
    log_detail "腳本路徑: $extract_script"
    
    # 建構解壓縮命令參數
    local extract_args=()
    if [ -n "$OUTPUT_DIR" ]; then
        extract_args+=("-o" "$OUTPUT_DIR")
    fi
    if [ "$FORCE_OVERWRITE" = true ]; then
        extract_args+=("-f")
    fi
    if [ "$VERBOSE" = true ]; then
        extract_args+=("-v")
    elif [ "$QUIET" = true ]; then
        extract_args+=("-q")
    fi
    # extract-archive.sh v2.0 不再包含驗證功能，無需額外參數
    extract_args+=("$file_path")
    
    # 執行解壓縮
    local start_time end_time duration
    start_time=$(date +%s.%3N)
    
    if bash "$extract_script" "${extract_args[@]}"; then
        end_time=$(date +%s.%3N)
        duration=$(echo "scale=2; $end_time - $start_time" | bc)
        echo
        log_success "解壓縮階段完成 (耗時: ${duration}s)"
        return 0
    else
        end_time=$(date +%s.%3N)
        duration=$(echo "scale=2; $end_time - $start_time" | bc)
        echo
        log_error "解壓縮階段失敗 (耗時: ${duration}s)"
        return 1
    fi
}

# 顯示最終統計
show_final_stats() {
    local file_path="$1"
    local start_time="$2"
    local output_dir="$3"
    local end_time
    end_time=$(date +%s.%3N)
    
    if [ "$QUIET" = false ]; then
        echo
        print_separator
        log_info "完成統計報告"
        print_separator
        
        # 檔案資訊
        log_info "處理檔案: $(basename "$file_path")"
        if [ "$VERIFY_ONLY" = false ] && [ -n "$output_dir" ]; then
            log_info "輸出目錄: $output_dir"
        fi
        
        # 時間資訊
        local total_time
        total_time=$(echo "scale=2; $end_time - $start_time" | bc)
        log_info "總計時間: ${total_time}s"
        
        # 階段資訊
        if [ "$SKIP_VERIFY" = false ]; then
            log_success "完整性驗證: 通過"
        else
            log_warning "完整性驗證: 已跳過"
        fi
        
        if [ "$VERIFY_ONLY" = false ]; then
            log_success "安全解壓縮: 完成"
        fi
        
        print_separator
    fi
}

# 驗證輸入參數
validate_input() {
    # 檢查是否提供了檔案路徑
    if [ -z "$TARGET_FILE" ]; then
        log_error "錯誤: 需要指定要處理的檔案"
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
    
    # 檢查衝突選項
    if [ "$VERIFY_ONLY" = true ] && [ "$SKIP_VERIFY" = true ]; then
        log_error "錯誤: --verify-only 與 --skip-verify 不能同時使用"
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
    
    # 檢查腳本依賴
    check_script_dependencies
    
    # 顯示開始資訊
    if [ "$QUIET" = false ]; then
        log_info "驗證與解壓縮工具 v1.0 - 冷儲存封存檔案安全處理"
        if [ "$VERIFY_ONLY" = true ]; then
            log_info "模式: 僅驗證"
        elif [ "$SKIP_VERIFY" = true ]; then
            log_info "模式: 僅解壓縮 (跳過驗證)"
        else
            log_info "模式: 完整處理 (驗證 + 解壓縮)"
        fi
        echo
    fi
    
    # 顯示檔案資訊
    show_file_info "$TARGET_FILE"
    
    # 執行驗證階段
    if [ "$SKIP_VERIFY" = false ]; then
        if ! execute_verification "$TARGET_FILE"; then
            log_error "驗證失敗，停止處理"
            exit 1
        fi
    else
        log_warning "已跳過驗證階段 (不建議)"
    fi
    
    # 執行解壓縮階段
    local final_output_dir=""
    if [ "$VERIFY_ONLY" = false ]; then
        if ! execute_extraction "$TARGET_FILE"; then
            log_error "解壓縮失敗"
            exit 1
        fi
        
        # 計算最終輸出目錄
        if [ -n "$OUTPUT_DIR" ]; then
            final_output_dir="$OUTPUT_DIR"
        else
            local file_basename
            file_basename=$(basename "$TARGET_FILE" .tar.zst)
            final_output_dir="./$file_basename"
        fi
    fi
    
    # 顯示最終統計
    show_final_stats "$TARGET_FILE" "$start_time" "$final_output_dir"
    
    # 成功完成
    if [ "$VERIFY_ONLY" = true ]; then
        log_success "驗證完成！檔案完整性確認無誤"
    else
        log_success "處理完成！檔案已驗證並解壓縮到: $final_output_dir"
    fi
    
    exit 0
}

# 執行主函數
main "$@" 