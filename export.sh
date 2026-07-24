#!/bin/bash
set -e

# Student Analysis Platform - Export Script (Linux/WSL)
# Usage: bash export.sh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPORT_DIR="$PROJECT_DIR/export"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE="$EXPORT_DIR/student_analysis_${TIMESTAMP}.zip"

# Excluded directories
EXCLUDE_DIRS=('__pycache__' 'venv' '.venv' '.git' '.idea' '.vscode' 'uploads' 'logs' 'export' 'new-datas' '---bak---' 'dist' 'build' 'node_modules')

echo
echo "============================================================"
echo "  Export Package"
echo "============================================================"
echo

mkdir -p "$EXPORT_DIR"

echo "[1/3] Cleaning temp files..."
find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null
find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "      Done"

echo
echo "[2/3] Packaging..."

# Build exclusion arguments for zip
EXCLUDE_ARGS=()
for dir in "${EXCLUDE_DIRS[@]}"; do
    EXCLUDE_ARGS+=(-x "*/${dir}/*")
done
# Also exclude common junk
EXCLUDE_ARGS+=(-x "*.pyc" -x "*.zip" -x "*.tar.gz" -x "*.rar" -x "*.7z" -x "*.log" -x "Thumbs.db" -x "desktop.ini")

cd "$PROJECT_DIR"
zip -r "$OUTPUT_FILE" . "${EXCLUDE_ARGS[@]}"

echo "      Done: $OUTPUT_FILE"

echo
echo "[3/3] Complete"
echo
echo "============================================================"
echo "  Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo "  Package: $OUTPUT_FILE"
echo "============================================================"
echo

echo "Done. Press any key to exit..."
read -n 1
