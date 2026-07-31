# -*- coding: utf-8 -*-
"""
教学过程智能分析与预警平台 - 配置文件
"""
import os
import secrets
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据库配置
# 用户名和密码不提供默认值，非测试环境必须显式配置。
MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
try:
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
except ValueError as error:
    raise RuntimeError('MYSQL_PORT must be an integer') from error
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'student_analysis')

from urllib.parse import quote_plus

# 对密码进行URL编码，处理特殊字符
_encoded_user = quote_plus(MYSQL_USER or '')
_encoded_password = quote_plus(MYSQL_PASSWORD or '')
SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{_encoded_user}:{_encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4'
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False  # 生产环境关闭SQL日志

# Flask配置
DEBUG = True

_DEVELOPMENT_SECRET_KEY = secrets.token_urlsafe(32)
_TESTING_SECRET_KEY = secrets.token_urlsafe(32)

# 文件上传配置
UPLOAD_FOLDER = BASE_DIR / 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
STUDENT_IMAGE_FOLDER = UPLOAD_FOLDER / 'student_images'
STUDENT_IMAGE_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
STUDENT_IMAGE_MAX_FILE_SIZE = 5 * 1024 * 1024
STUDENT_IMAGE_MAX_BATCH_FILES = 200
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

# 日志配置
LOG_FOLDER = BASE_DIR / 'logs'
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# 外部Excel数据文件配置（用于直接读取未入库的明细数据）
EDUCODER_ASSIGNMENT_FILE = os.environ.get(
    'EDUCODER_ASSIGNMENT_FILE',
    '程序设计与数据结构(二)_(数据结构_C++描述）2026春_头歌_作业成绩表.xlsx'
)

# 风险预警配置
WARNING_RULES = {
    'attendance_rate': {
        'threshold': 60,
        'level': 1,
        'message': '到课率过低'
    },
    'video_finish_rate': {
        'threshold': 40,
        'level': 1,
        'message': '视频完成率过低'
    },
    'avg_experiment_score': {
        'threshold': 50,
        'level': 1,
        'message': '实验平均分过低'
    },
    'theory_practice_diff': {
        'threshold': 30,
        'level': 2,
        'message': '理论与实践偏差过大'
    }
}

# 风险等级定义
WARNING_LEVELS = {
    0: '正常',    # 0-30
    1: '关注',    # 30-60
    2: '预警',    # 60-80
    3: '高危'     # 80-100
}


class Config:
    """基础配置"""
    SECRET_KEY = None
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = SQLALCHEMY_TRACK_MODIFICATIONS
    UPLOAD_FOLDER = str(UPLOAD_FOLDER)
    STUDENT_IMAGE_FOLDER = str(STUDENT_IMAGE_FOLDER)
    STUDENT_IMAGE_ALLOWED_EXTENSIONS = STUDENT_IMAGE_ALLOWED_EXTENSIONS
    STUDENT_IMAGE_MAX_FILE_SIZE = STUDENT_IMAGE_MAX_FILE_SIZE
    STUDENT_IMAGE_MAX_BATCH_FILES = STUDENT_IMAGE_MAX_BATCH_FILES
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')


class DevelopmentConfig(Config):
    """开发环境配置"""
    SECRET_KEY = _DEVELOPMENT_SECRET_KEY
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    """测试环境配置"""
    SECRET_KEY = _TESTING_SECRET_KEY
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'test': TestingConfig
}


def get_ephemeral_secret_key(config_name: str):
    return {
        'dev': _DEVELOPMENT_SECRET_KEY,
        'test': _TESTING_SECRET_KEY,
    }.get(config_name)


def validate_database_environment() -> None:
    """在 MySQL 初始化前拒绝缺失的运行时凭据。"""
    required_variables = ('MYSQL_USER', 'MYSQL_PASSWORD')
    missing = [
        name for name in required_variables
        if not os.environ.get(name, '').strip()
    ]
    if missing:
        raise RuntimeError(
            'Missing required MySQL configuration: ' + ', '.join(missing)
        )
