#!/bin/bash
# ============================================================
#  教学过程智能分析与预警平台 - 一键启动脚本 (Linux)
#  功能：激活虚拟环境 → 检查数据库 → 初始化 → 启动服务
#  用法：chmod +x start.sh && ./start.sh
# ============================================================

set -e

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo
echo "============================================================"
echo "  教学过程智能分析与预警平台"
echo "============================================================"
echo

# ---- 1. 激活虚拟环境 ----
VENV_DIR="venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "[1/4] 激活虚拟环境..."
    source "$VENV_DIR/bin/activate"
    echo "      虚拟环境已激活: $VENV_DIR"
else
    echo "[1/4] 未找到虚拟环境，使用系统 Python"
    echo "      提示: 运行 python3 -m venv venv 可创建虚拟环境"
fi

# ---- 2. 检查 MySQL 连接 ----
echo
echo "[2/4] 检查 MySQL 数据库连接..."

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-Root@123456}"
MYSQL_DATABASE="${MYSQL_DATABASE:-student_analysis}"

if python3 -c "
import pymysql
pymysql.connect(host='$MYSQL_HOST', port=$MYSQL_PORT, user='$MYSQL_USER', password='$MYSQL_PASSWORD', charset='utf8mb4').close()
print('       MySQL 连接正常')
" 2>/dev/null; then
    # ---- 3. 初始化数据库（如果需要） ----
    echo
    echo "[3/4] 初始化数据库表结构..."
    if python3 init_database.py --tables-only 2>/dev/null; then
        echo "      数据库表结构就绪"
    else
        echo "      表结构可能已存在，跳过"
    fi
else
    echo "      [警告] MySQL 连接失败，请确保 MySQL 服务已启动"
    echo "      使用默认密码 'Root@123456'，可通过环境变量覆盖:"
    echo "        export MYSQL_PASSWORD=your_password"
    echo "      或者：docker start mysql-container"
    echo
    read -p "是否继续启动（跳过数据库检查）？[y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# ---- 4. 启动 Flask 开发服务器 ----
echo
echo "[4/4] 启动 Flask 开发服务器..."
echo
echo "============================================================"
echo "  服务地址: http://localhost:5000"
echo "  按 Ctrl+C 停止服务"
echo "============================================================"
echo

python3 app.py
