#!/usr/bin/env bash
set -euo pipefail

export ADMIN_USERNAME='admin'
export ADMIN_PASSWORD_HASH='scrypt:32768:8:1$B74TIIlSwkU9cMFx$c2df4abbf9272c6a75e7293171c6ee547cccc49826e1249f45278130411ed9ee9f9a604f4bd9c49057f290c59f0d8e1df3b1344f0265dbc16c2116c2fada9892'
#export FLASK_ENV='prod'
#export SECRET_KEY='粘贴生成的随机密钥'
#export SESSION_COOKIE_SECURE=true
export MYSQL_USER='root'
export MYSQL_PASSWORD='Root@123456'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo
echo "============================================================"
echo "  教学过程智能分析与预警平台"
echo "============================================================"
echo

require_env() {
    local variable_name="$1"
    local guidance="$2"
    if [ -z "${!variable_name:-}" ]; then
        echo "[错误] 缺少 ${variable_name}。${guidance}" >&2
        exit 2
    fi
}

# 必需的登录凭据必须在任何数据库访问之前检查。
require_env ADMIN_USERNAME "请先设置管理员用户名。"
require_env ADMIN_PASSWORD_HASH "请使用 Werkzeug 生成密码哈希后设置。"
require_env MYSQL_USER "请设置专用数据库用户名。"
require_env MYSQL_PASSWORD "请设置数据库密码。"

# 生产环境必须提供持久、高熵密钥；HTTPS 会话 Cookie 强制仅通过安全连接发送。
if [ "${FLASK_ENV:-dev}" = "prod" ]; then
    require_env SECRET_KEY "请设置独立的高熵随机密钥。"
    export SESSION_COOKIE_SECURE=true
fi

if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif [ -x "venv/bin/python" ]; then
    PYTHON_BIN="venv/bin/python"
else
    PYTHON_BIN="python3"
fi

if ! "$PYTHON_BIN" -c "from config import validate_database_environment; validate_database_environment()" 2>/dev/null; then
    echo "[错误] MYSQL_USER 和 MYSQL_PASSWORD 必须是非空白值，MYSQL_PORT 必须有效。" >&2
    exit 2
fi

echo "[1/3] 检查 MySQL 连接..."
"$PYTHON_BIN" -c "import pymysql; from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD; pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, charset='utf8mb4').close(); print('      MySQL 连接正常')"

echo "[2/3] 创建缺失的数据库表（不会删除或重建数据库）..."
"$PYTHON_BIN" init_database.py --tables-only

echo "[3/3] 启动 Web 服务..."
echo "      服务地址: http://localhost:5000"
if [ "${FLASK_ENV:-dev}" = "prod" ]; then
    echo "      使用 Waitress 生产 WSGI 服务器"
    exec "$PYTHON_BIN" -m waitress --listen=0.0.0.0:5000 app:app
fi

echo "      使用 Flask 开发服务器"
exec "$PYTHON_BIN" app.py
