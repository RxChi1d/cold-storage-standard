#!/bin/bash

# 批量處理7z檔案的腳本
# 功能：對指定資料夾中的每個7z檔案執行coldstore pack命令

set -e  # 遇到錯誤立即退出

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 輔助函數
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 顯示使用說明
show_usage() {
    echo "使用方法: $0 <輸入資料夾路徑> [輸出資料夾路徑]"
    echo
    echo "功能："
    echo "  對指定資料夾中的每個7z檔案執行 'coldstore pack' 命令"
    echo
    echo "參數："
    echo "  <輸入資料夾路徑>    包含7z檔案的目錄路徑"
    echo "  [輸出資料夾路徑]    處理後檔案的輸出目錄 (可選，預設為 'processed')"
    echo
    echo "範例："
    echo "  $0 /path/to/archives                          # 輸出到預設目錄 'processed'"
    echo "  $0 /path/to/archives /path/to/output          # 輸出到指定目錄"
    echo "  $0 . ./output                                 # 當前目錄的7z檔案輸出到 ./output"
}

# 檢查參數
if [ $# -eq 0 ]; then
    log_error "缺少輸入資料夾路徑參數"
    echo
    show_usage
    exit 1
fi

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_usage
    exit 0
fi

INPUT_DIR="$1"
OUTPUT_DIR="${2:-processed}"  # 如果沒有提供第二個參數，使用預設值 "processed"

# 檢查輸入目錄是否存在
if [ ! -d "$INPUT_DIR" ]; then
    log_error "輸入目錄不存在: $INPUT_DIR"
    exit 1
fi

# 轉換為絕對路徑
INPUT_DIR=$(cd "$INPUT_DIR" && pwd)
log_info "輸入目錄: $INPUT_DIR"

# 創建輸出目錄（如果不存在）
if [ ! -d "$OUTPUT_DIR" ]; then
    log_info "創建輸出目錄: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR" || {
        log_error "無法創建輸出目錄: $OUTPUT_DIR"
        exit 1
    }
fi

# 轉換輸出目錄為絕對路徑
OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd)
log_info "輸出目錄: $OUTPUT_DIR"

# 檢查coldstore命令是否可用
if ! command -v coldstore &> /dev/null; then
    log_error "找不到 coldstore 命令。請確保已安裝並在PATH中"
    exit 1
fi

# 切換到輸入目錄
cd "$INPUT_DIR"

# 找出所有7z檔案並計數
seven_zip_count=0
temp_file=$(mktemp)
find . -maxdepth 1 -name "*.7z" -type f | sort > "$temp_file"

# 計算檔案數量
while IFS= read -r line; do
    seven_zip_count=$((seven_zip_count + 1))
done < "$temp_file"

if [ $seven_zip_count -eq 0 ]; then
    log_warning "在目錄 $INPUT_DIR 中沒有找到任何7z檔案"
    rm -f "$temp_file"
    exit 0
fi

log_info "找到 $seven_zip_count 個7z檔案"

# 處理每個7z檔案
success_count=0
error_count=0

while IFS= read -r file; do
    # 移除 ./ 前綴
    clean_filename="${file#./}"

    log_info "正在處理: $clean_filename -> $OUTPUT_DIR"

    if coldstore pack -o "$OUTPUT_DIR" "$clean_filename"; then
        log_success "成功處理: $clean_filename"
        success_count=$((success_count + 1))
    else
        log_error "處理失敗: $clean_filename"
        error_count=$((error_count + 1))
    fi

    echo  # 空行分隔
done < "$temp_file"

# 清理臨時檔案
rm -f "$temp_file"

# 顯示結果摘要
echo "======== 處理結果摘要 ========"
log_info "總檔案數: $seven_zip_count"
log_success "成功: $success_count"
if [ $error_count -gt 0 ]; then
    log_error "失敗: $error_count"
fi

if [ $error_count -eq 0 ]; then
    log_success "所有檔案處理完成！"
    exit 0
else
    log_warning "部分檔案處理失敗，請檢查錯誤訊息"
    exit 1
fi
