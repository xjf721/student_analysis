# -*- coding: utf-8 -*-
"""
Controllers package - 控制器层
"""
from .dashboard_controller import dashboard_bp
from .student_controller import student_bp
from .knowledge_controller import knowledge_bp
from .warning_controller import warning_bp
from .import_controller import import_bp

__all__ = [
    'dashboard_bp',
    'student_bp',
    'knowledge_bp',
    'warning_bp',
    'import_bp'
]
