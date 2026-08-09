# -*- coding: utf-8 -*-
"""
教学过程智能分析与预警平台 - 主应用入口
"""
import os
import logging
from pathlib import Path
from flask import Flask

from config import (
    config_by_name,
    get_ephemeral_secret_key,
    validate_database_environment,
)
from extensions import csrf, limiter
from models import init_db
from controllers import (
    auth_bp, classes_bp, dashboard_bp, import_bp, knowledge_bp,
    student_bp, student_image_bp, warning_bp,
)
from services.class_context import install_request_guards, install_template_context


def create_app(config_name: str = 'dev', overrides: dict = None) -> Flask:
    """
    创建Flask应用实例
    
    Args:
        config_name: 配置名称 (dev/prod/test)
        
    Returns:
        Flask应用实例
    """
    app = Flask(__name__)
    
    # 加载配置
    app.config.from_object(config_by_name[config_name])
    environment_secret = os.environ.get('SECRET_KEY')
    if environment_secret:
        app.config['SECRET_KEY'] = environment_secret
    if overrides:
        app.config.update(overrides)

    if not app.config.get('SECRET_KEY'):
        ephemeral_secret = get_ephemeral_secret_key(config_name)
        if ephemeral_secret:
            app.config['SECRET_KEY'] = ephemeral_secret
        else:
            raise RuntimeError('SECRET_KEY must be configured for production')

    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('mysql'):
        validate_database_environment()

    csrf.init_app(app)
    limiter.init_app(app)
    
    # 确保必要的目录存在
    ensure_directories(app)
    
    # 配置日志
    setup_logging(app)
    
    # 初始化数据库
    init_db(app)
    
    # 注册蓝图
    register_blueprints(app)

    install_request_guards(app)
    install_template_context(app)
    
    # 注册错误处理
    register_error_handlers(app)
    
    return app


def ensure_directories(app: Flask) -> None:
    """确保必要的目录存在"""
    directories = [
        app.config.get('UPLOAD_FOLDER', 'uploads'),
        app.config['STUDENT_IMAGE_FOLDER'],
        'logs',
        'static',
        'templates'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)


def setup_logging(app: Flask) -> None:
    """配置日志"""
    log_folder = Path('logs')
    log_folder.mkdir(parents=True, exist_ok=True)
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_file = log_folder / 'system.log'
    
    # 配置根日志
    logging.basicConfig(
        level=getattr(logging, app.config.get('LOG_LEVEL', 'INFO')),
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 设置SQLAlchemy日志
    if not app.config.get('SQLALCHEMY_ECHO'):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def register_blueprints(app: Flask) -> None:
    """注册蓝图"""
    app.register_blueprint(auth_bp)
    app.register_blueprint(classes_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(warning_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(student_image_bp)


def register_error_handlers(app: Flask) -> None:
    """注册错误处理"""
    from flask import render_template
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500


# 创建应用实例
app = create_app(os.environ.get('FLASK_ENV', 'dev'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
