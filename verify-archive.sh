#!/bin/bash
# 完整性檢查腳本 - 冷儲存封存檔案驗證工具
# 作者: AI Assistant
# 版本: v1.0
# 用途: 對 tar.zst 檔案及其相關檔案進行完整性驗證
#
# [VERIFY] 驗證項目：
# 1. zstd 檔案完整性檢查
# 2. SHA-256 雜湊驗證
# 3. BLAKE3 雜湊驗證
# 4. PAR2 冗餘完整性檢查
# 5. tar 內容結構驗證
#
# [USAGE] 使用方式:
# ./verify-archive.sh file.tar.zst              # 驗證單一檔案
# ./verify-archive.sh *.tar.zst                 # 批量驗證
# ./verify-archive.sh -d /path/to/directory     # 驗證目錄中所有檔案

# 顯示使用說明
show_usage() {
    cat << EOF
使用方法: $0 [選項] [檔案路徑...]

參數:
  檔案路徑                tar.zst 檔案路徑 (支援多個檔案或萬用字元)

選項:
  -d, --directory DIR     驗證指定目錄中的所有 tar.zst 檔案
  -v, --verbose          顯示詳細驗證資訊
  -q, --quiet            安靜模式，只顯示結果
  -h, --help             顯示此說明

驗證項目:
  + zstd 檔案完整性檢查
  + SHA-256 雜湊驗證
  + BLAKE3 雜湊驗證  
  + PAR2 冗餘完整性檢查
  + tar 內容結構驗證

範例:
  $0 archive.tar.zst                    # 驗證單一檔案
  $0 *.tar.zst                          # 驗證當前目錄所有檔案
  $0 -d ./processed                     # 驗證目錄中所有檔案
  $0 -v archive.tar.zst                 # 詳細模式驗證
  $0 -q *.tar.zst                       # 安靜模式批量驗證

[SYSTEM] 系統需求:
  工具依賴: zstd, sha256sum, b3sum, par2, tar
EOF
}

# 預設參數
VERBOSE=false
QUIET=false
TARGET_DIRECTORY=""
TARGET_FILES=()

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
        printf "${COLOR_CYAN}%s${COLOR_RESET}\n" "$1"
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
        printf "${COLOR_BLUE}%s${COLOR_RESET}\n" "$1"
    fi
}

# 解析命令列參數
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--directory)
                shift
                if [[ -n "$1" && -d "$1" ]]; then
                    TARGET_DIRECTORY="$1"
                    shift
                else
                    log_error "錯誤: --directory 需要指定有效的目錄路徑"
                    exit 1
                fi
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
                if [[ -f "$1" ]]; then
                    TARGET_FILES+=("$1")
                else
                    log_warning "檔案不存在，跳過: $1"
                fi
                shift
                ;;
        esac
    done
}

# 檢查必要工具
check_required_tools() {
    local missing=()
    
    for tool in zstd sha256sum b3sum par2 tar; do
        if ! command -v "$tool" &> /dev/null; then
            missing+=("$tool")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "缺少必要工具: ${missing[*]}"
        log_info ""
        log_info "安裝建議 (Ubuntu/Debian):"
        log_info "sudo apt update && apt install zstd par2cmdline b3sum"
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

# 驗證 zstd 檔案完整性
verify_zstd_integrity() {
    local file_path="$1"
    
    log_step "驗證 zstd 檔案完整性..."
    
    # 檢查檔案是否存在
    if [ ! -f "$file_path" ]; then
        log_error "檔案不存在: $file_path"
        return 1
    fi
    
    # 執行 zstd 測試（需要 --long=31 參數以匹配壓縮時的設定）
    local start_time end_time
    start_time=$(date +%s.%3N)
    
    if zstd -tq --long=31 "$file_path" 2>/dev/null; then
        end_time=$(date +%s.%3N)
        local duration
        duration=$(echo "scale=3; $end_time - $start_time" | bc)
        log_success "zstd 完整性驗證通過 (耗時: ${duration}s)"
        return 0
    else
        log_error "zstd 完整性驗證失敗"
        return 1
    fi
}

# 驗證 SHA-256 雜湊
verify_sha256_hash() {
    local file_path="$1"
    local hash_file="$file_path.sha256"
    
    log_step "驗證 SHA-256 雜湊..."
    
    if [ ! -f "$hash_file" ]; then
        log_warning "SHA-256 雜湊檔案不存在: $hash_file"
        return 1
    fi
    
    local expected_hash actual_hash
    expected_hash=$(cut -d' ' -f1 "$hash_file")
    actual_hash=$(sha256sum "$file_path" | cut -d' ' -f1)
    
    if [ "$expected_hash" = "$actual_hash" ]; then
        log_success "SHA-256 雜湊驗證通過"
        log_detail "雜湊值: $actual_hash"
        return 0
    else
        log_error "SHA-256 雜湊驗證失敗"
        log_detail "預期雜湊: $expected_hash"
        log_detail "實際雜湊: $actual_hash"
        return 1
    fi
}

# 驗證 BLAKE3 雜湊
verify_blake3_hash() {
    local file_path="$1"
    local hash_file="$file_path.blake3"
    
    log_step "驗證 BLAKE3 雜湊..."
    
    if [ ! -f "$hash_file" ]; then
        log_warning "BLAKE3 雜湊檔案不存在: $hash_file"
        return 1
    fi
    
    local expected_hash actual_hash
    expected_hash=$(cut -d' ' -f1 "$hash_file")
    actual_hash=$(b3sum "$file_path" | cut -d' ' -f1)
    
    if [ "$expected_hash" = "$actual_hash" ]; then
        log_success "BLAKE3 雜湊驗證通過"
        log_detail "雜湊值: $actual_hash"
        return 0
    else
        log_error "BLAKE3 雜湊驗證失敗"
        log_detail "預期雜湊: $expected_hash"
        log_detail "實際雜湊: $actual_hash"
        return 1
    fi
}

# 驗證 PAR2 冗餘
verify_par2_redundancy() {
    local file_path="$1"
    local par2_file="$file_path.par2"
    
    log_step "驗證 PAR2 冗餘完整性..."
    
    if [ ! -f "$par2_file" ]; then
        log_warning "PAR2 檔案不存在: $par2_file"
        return 1
    fi
    
    # 執行 PAR2 驗證
    local verify_output
    if verify_output=$(par2 verify "$par2_file" 2>&1); then
        log_success "PAR2 冗餘驗證通過"
        log_detail "PAR2 狀態: 檔案完整，無需修復"
        return 0
    else
        # 檢查是否可修復
        if echo "$verify_output" | grep -q "repairable"; then
            log_warning "PAR2 檢測到錯誤但可修復"
            log_detail "建議執行: par2 repair $par2_file"
            return 2  # 特殊返回碼表示可修復
        else
            log_error "PAR2 冗餘驗證失敗"
            log_detail "PAR2 輸出: $verify_output"
            return 1
        fi
    fi
}

# 驗證 tar 內容結構
verify_tar_content() {
    local file_path="$1"
    
    log_step "驗證 tar 內容結構..."
    
    # 解壓縮並驗證 tar 內容（使用正確的參數）
    if zstd -dc --long=31 "$file_path" | tar -tvf - > /dev/null 2>&1; then
        log_success "tar 內容結構驗證通過"
        
        # 如果在詳細模式，顯示檔案數量
        if [ "$VERBOSE" = true ]; then
            local file_count
            file_count=$(zstd -dc --long=31 "$file_path" | tar -tf - | wc -l)
            log_detail "包含檔案數量: $file_count"
        fi
        return 0
    else
        log_error "tar 內容結構驗證失敗"
        return 1
    fi
}

# 驗證單一檔案
verify_single_file() {
    local file_path="$1"
    local file_name
    file_name=$(basename "$file_path")
    
    # 檢查檔案副檔名
    if [[ ! "$file_path" =~ \.tar\.zst$ ]]; then
        log_warning "跳過非 tar.zst 檔案: $file_name"
        return 2
    fi
    
    if [ "$QUIET" = false ]; then
        print_separator
        log_info "檔案: $file_name"
        
        # 顯示檔案資訊
        if [ -f "$file_path" ]; then
            local file_size
            file_size=$(stat -c%s "$file_path")
            log_info "大小: $(format_size "$file_size")"
        fi
        print_separator
    fi
    
    # 執行各項驗證
    local results=()
    local overall_result=0
    
    # 1. zstd 完整性驗證
    if verify_zstd_integrity "$file_path"; then
        results+=("zstd:PASS")
    else
        results+=("zstd:FAIL")
        overall_result=1
    fi
    
    # 2. SHA-256 驗證
    local sha256_result
    sha256_result=$(verify_sha256_hash "$file_path")
    case $? in
        0) results+=("SHA256:PASS") ;;
        1) results+=("SHA256:FAIL"); overall_result=1 ;;
        *) results+=("SHA256:SKIP") ;;
    esac
    
    # 3. BLAKE3 驗證
    local blake3_result
    blake3_result=$(verify_blake3_hash "$file_path")
    case $? in
        0) results+=("BLAKE3:PASS") ;;
        1) results+=("BLAKE3:FAIL"); overall_result=1 ;;
        *) results+=("BLAKE3:SKIP") ;;
    esac
    
    # 4. PAR2 驗證
    local par2_result
    par2_result=$(verify_par2_redundancy "$file_path")
    case $? in
        0) results+=("PAR2:PASS") ;;
        1) results+=("PAR2:FAIL"); overall_result=1 ;;
        2) results+=("PAR2:REPAIRABLE"); overall_result=1 ;;
        *) results+=("PAR2:SKIP") ;;
    esac
    
    # 5. tar 內容驗證
    if verify_tar_content "$file_path"; then
        results+=("TAR:PASS")
    else
        results+=("TAR:FAIL")
        overall_result=1
    fi
    
    # 顯示驗證摘要
    if [ "$QUIET" = false ]; then
        print_separator
        log_info "驗證摘要: $file_name"
        for result in "${results[@]}"; do
            local test_name="${result%:*}"
            local test_result="${result#*:}"
            case "$test_result" in
                "PASS") log_success "$test_name: 通過" ;;
                "FAIL") log_error "$test_name: 失敗" ;;
                "REPAIRABLE") log_warning "$test_name: 可修復" ;;
                "SKIP") log_warning "$test_name: 跳過" ;;
            esac
        done
        print_separator
    fi
    
    # 總體結果
    if [ $overall_result -eq 0 ]; then
        log_success "檔案驗證完全通過: $file_name"
    else
        log_error "檔案驗證失敗: $file_name"
    fi
    
    return $overall_result
}

# 收集目標檔案
collect_target_files() {
    if [ -n "$TARGET_DIRECTORY" ]; then
        # 從目錄收集檔案
        log_info "搜尋目錄: $TARGET_DIRECTORY"
        
        while IFS= read -r -d '' file; do
            TARGET_FILES+=("$file")
        done < <(find "$TARGET_DIRECTORY" -name "*.tar.zst" -type f -print0 2>/dev/null)
        
        if [ ${#TARGET_FILES[@]} -eq 0 ]; then
            log_warning "在目錄中找不到 tar.zst 檔案: $TARGET_DIRECTORY"
            return 1
        fi
        
        log_info "找到 ${#TARGET_FILES[@]} 個檔案"
    fi
    
    if [ ${#TARGET_FILES[@]} -eq 0 ]; then
        log_error "沒有指定要驗證的檔案"
        echo "使用 $0 --help 查看使用說明" >&2
        return 1
    fi
    
    return 0
}

# 主要處理函數
main() {
    # 解析參數
    parse_arguments "$@"
    
    # 收集目標檔案
    if ! collect_target_files; then
        exit 1
    fi
    
    # 檢查必要工具
    check_required_tools
    
    # 顯示開始資訊
    if [ "$QUIET" = false ]; then
        log_info "完整性檢查工具 v1.0 - 冷儲存封存檔案驗證"
        log_info "準備驗證 ${#TARGET_FILES[@]} 個檔案"
        echo
    fi
    
    # 執行驗證
    local success_count=0
    local error_count=0
    local start_time
    start_time=$(date +%s.%3N)
    
    for file_path in "${TARGET_FILES[@]}"; do
        if verify_single_file "$file_path"; then
            ((success_count++))
        else
            ((error_count++))
        fi
        
        if [ "$QUIET" = false ] && [ ${#TARGET_FILES[@]} -gt 1 ]; then
            echo
        fi
    done
    
    # 顯示總結
    local end_time total_time
    end_time=$(date +%s.%3N)
    total_time=$(echo "scale=2; $end_time - $start_time" | bc)
    
    if [ "$QUIET" = false ]; then
        print_separator
        log_info "驗證完成摘要"
        print_separator
        log_info "總計檔案: ${#TARGET_FILES[@]}"
        log_success "成功: $success_count"
        if [ $error_count -gt 0 ]; then
            log_error "失敗: $error_count"
        fi
        log_info "處理時間: ${total_time}s"
        print_separator
    fi
    
    # 返回適當的退出碼
    if [ $error_count -eq 0 ]; then
        if [ "$QUIET" = false ]; then
            log_success "所有檔案驗證通過！"
        fi
        exit 0
    else
        if [ "$QUIET" = false ]; then
            log_error "有 $error_count 個檔案驗證失敗"
        fi
        exit 1
    fi
}

# 執行主函數
main "$@" 