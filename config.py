# -*- coding: utf-8 -*-
"""
教学过程智能分析与预警平台 - 配置文件
"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据库配置
# MySQL运行在Docker中，根据实际情况修改
MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', 'Root@123456')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'student_analysis')

from urllib.parse import quote_plus

# 对密码进行URL编码，处理特殊字符
_encoded_password = quote_plus(MYSQL_PASSWORD)
SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{MYSQL_USER}:{_encoded_password}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4'
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False  # 生产环境关闭SQL日志

# Flask配置
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = True

# 文件上传配置
UPLOAD_FOLDER = BASE_DIR / 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 最大16MB

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
    SECRET_KEY = SECRET_KEY
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = SQLALCHEMY_TRACK_MODIFICATIONS
    UPLOAD_FOLDER = str(UPLOAD_FOLDER)
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    WTF_CSRF_ENABLED = False
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    SQLALCHEMY_ECHO = False


class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


config_by_name = {
    'dev': DevelopmentConfig,
    'prod': ProductionConfig,
    'test': TestingConfig
}
