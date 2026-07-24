# 教学过程智能分析与预警平台

基于 Flask + MySQL 的多平台教学数据聚合、学生学习画像分析与风险预警系统。支持导入 **雨课堂** 和 **EduCoder（头歌）** 导出的 Excel 数据，自动生成仪表盘、雷达图、热力图及学生个体画像，并提供风险等级评分与预警。

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.9+ | 建议 3.10+ |
| MySQL | 8.0 | 数据库服务 |
| pip | 最新 | Python 包管理器 |

> **注意：** 项目源代码使用全中文注释，路径中包含中文不影响 WSL/Linux 环境运行。

## 快速开始

### 1. 克隆项目并进入目录

```bash
cd student_analysis
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv

# Linux / WSL / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. 配置数据库

确保 MySQL 服务已启动，默认连接参数：

| 参数 | 默认值 |
|------|--------|
| Host | localhost |
| Port | 3306 |
| User | root |
| Password | Root@123456 |
| Database | student_analysis |

可通过环境变量覆盖：

| 环境变量 | 说明 |
|----------|------|
| `MYSQL_HOST` | 数据库主机地址 |
| `MYSQL_PORT` | 数据库端口 |
| `MYSQL_USER` | 数据库用户名 |
| `MYSQL_PASSWORD` | 数据库密码 |
| `MYSQL_DATABASE` | 数据库名称 |

### 4. 初始化数据库

```bash
python init_database.py
```

> 如需重建数据库，使用 `python init_database.py --reset`

### 5. 启动应用

```bash
python app.py
```

或使用一键启动脚本：

```bash
# WSL / Linux
bash start.sh

# Windows
start.bat
```

浏览器访问 **http://localhost:5000**。

## 数据导入流程

1. 访问「数据导入」页面
2. 上传雨课堂或 EduCoder 导出的 Excel 文件（支持批量上传）
3. 系统自动识别文件类型、解析数据并执行分析
4. 分析完成后可在各页面查看结果

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask 3.x |
| ORM | SQLAlchemy + Flask-SQLAlchemy |
| 数据库 | MySQL 8 |
| 数据分析 | Pandas |
| Excel 解析 | openpyxl + xlrd |
| 前端 | Bootstrap 5 + AdminLTE + ECharts |

## 项目结构

```
student_analysis/
├── app.py                  # 应用入口
├── config.py               # 配置（数据库、预警阈值等）
├── init_database.py        # 数据库初始化
├── requirements.txt        # Python 依赖
├── start.sh / start.bat    # 一键启动脚本
├── config/                 # 列名映射等配置文件
├── controllers/            # 路由控制器（Flask Blueprint）
├── models/                 # 数据模型（SQLAlchemy ORM）
├── repositories/           # 数据访问层
├── services/               # 业务逻辑层
│   ├── importers/          # Excel 导入器（插件式）
│   └── analysis/           # 分析引擎（行为、知识、实践、预警）
└── templates/              # Jinja2 前端模板
```

## 导出部署包

```bash
bash export.sh
```

生成的 ZIP 文件位于 `export/` 目录，不包含 `venv/`、`node_modules/` 等依赖目录，部署后需重新安装依赖。
