# 教学过程智能分析与预警平台

这是一个基于 Flask 与 MySQL 的多班级教学数据分析系统，支持雨课堂和头歌（EduCoder）Excel 导入、学生画像、知识分析、风险预警以及班级对比。

## 环境要求

- Python 3.9+（建议 3.10+）
- MySQL 8.0
- 项目依赖：`pip install -r requirements.txt`

Windows 可使用 `venv\Scripts\activate`，Linux、WSL 和 macOS 可使用 `source venv/bin/activate`。启动脚本也会识别项目内的 `.venv`。

## 必需配置

启动脚本在访问数据库之前检查管理员凭据；缺少配置时会明确报错并退出，不会使用默认管理员账号或密码。

1. 设置 `ADMIN_USERNAME`。
2. 使用 Werkzeug 的 `generate_password_hash` 生成 `ADMIN_PASSWORD_HASH`。以下命令交互式读取密码，不把明文密码写入命令历史：

   ```bash
   python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Admin password: ')))"
   ```

3. 生产环境设置 `FLASK_ENV=prod`，并生成独立、持久且高熵的 `SECRET_KEY`：

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

4. HTTPS 部署应设置 `SESSION_COOKIE_SECURE=true`。生产配置和启动脚本都会强制启用安全 Cookie；因此生产站点必须通过 HTTPS 访问，否则浏览器不会回传登录会话 Cookie。

PowerShell 示例：

```powershell
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD_HASH = "粘贴生成的 Werkzeug 哈希"
$env:FLASK_ENV = "prod"
$env:SECRET_KEY = "粘贴生成的随机密钥"
$env:SESSION_COOKIE_SECURE = "true"
```

Bash 示例：

```bash
export ADMIN_USERNAME='admin'
export ADMIN_PASSWORD_HASH='粘贴生成的 Werkzeug 哈希'
export FLASK_ENV='prod'
export SECRET_KEY='粘贴生成的随机密钥'
export SESSION_COOKIE_SECURE=true
```

数据库连接由 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD` 和 `MYSQL_DATABASE` 配置。生产部署应显式设置这些变量，并使用专用数据库账号。

## 数据库初始化与受控重建

非破坏性地创建缺失的数据库和表：

```bash
python init_database.py
```

只创建缺失的表：

```bash
python init_database.py --tables-only
```

结构升级需要清空独立目标数据库时，必须使用完整的受控重建命令：

```bash
python init_database.py --reset --confirm-reset DELETE-ALL-STUDENT-ANALYSIS-DATA
```

该操作会删除目标数据库中的全部数据且不可撤销。缺少确认短语或短语不完全一致时，命令会在连接数据库之前以参数错误退出。`start.bat` 和 `start.sh` 从不执行重建，只运行非破坏性的 `--tables-only`。

## 启动

完成环境变量配置后运行：

```bash
# Windows
start.bat

# Linux / WSL / macOS
bash start.sh
```

也可以直接运行 `python app.py`。默认服务地址为 <http://localhost:5000>。

## 首次导入与操作员验收

仓库不附带原始 `new-datas` 教学文件。完成受控重建后，请由操作员在独立测试数据库使用已授权的真实导出文件做以下验收，不要直接重建现有业务数据库：

1. 登录系统，创建“青年1班”和“青年2班”。
2. 分别进入两个班级的详情页，为每个班上传各自的雨课堂和头歌 Excel。
3. 切换到青年1班，记录首页学生数、学生列表首尾学号、知识点数和预警数。
4. 切换到青年2班，确认这些数据随班级变化，并确认搜索青年1班学生返回空。
5. 在青年2班上下文手工请求青年1班学生详情 ID，确认返回 404。
6. 打开班级对比页，确认两个班的聚合值分别等于各自首页值。
7. 归档一个班级，确认它离开快速切换列表，但仍可在班级管理页恢复。

同时逐班检查首页、学生、知识、预警与班级对比页面，确认导入记录和分析结果均绑定到当前班级。

## 项目结构

```text
student_analysis/
├── app.py
├── config.py
├── init_database.py
├── requirements.txt
├── start.sh / start.bat
├── controllers/
├── models/
├── repositories/
├── services/
└── templates/
```

## 导出部署包

```bash
bash export.sh
```

生成的 ZIP 文件位于 `export/` 目录，不包含虚拟环境或 `node_modules` 等依赖目录；部署后需重新安装依赖并重新设置上述环境变量。
