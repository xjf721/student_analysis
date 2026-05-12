# -*- coding: utf-8 -*-
"""
预警控制器

风险预警页面，包括：
- 预警学生列表
- 预警统计数据
- 预警类型分布
"""
from flask import Blueprint, render_template, jsonify, request
from repositories import WarningRepository
from services.analysis import WarningEngine

warning_bp = Blueprint('warning', __name__)


@warning_bp.route('/warning')
def warning_page():
    """风险预警页面"""
    return render_template('warning/index.html')


@warning_bp.route('/api/warning/students')
def get_warning_students():
    """
    获取预警学生列表
    
    Query Parameters:
        min_score: 最低风险指数（可选）
        limit: 返回数量（可选）
        
    Returns:
        预警学生列表
    """
    min_score = request.args.get('min_score', default=60.0, type=float)
    limit = request.args.get('limit', default=50, type=int)
    
    students = WarningRepository.get_high_risk_students(min_score=min_score, limit=limit)
    
    return jsonify(students)


@warning_bp.route('/api/warning/statistics')
def get_warning_statistics():
    """
    获取预警统计数据
    
    Query Parameters:
        class_id: 班级ID（可选）
        
    Returns:
        统计数据
    """
    class_id = request.args.get('class_id', type=int)
    
    stats = WarningRepository.get_statistics(class_id=class_id)
    
    return jsonify(stats)


@warning_bp.route('/api/warning/distribution')
def get_warning_distribution():
    """
    获取预警类型分布
    
    Returns:
        类型分布数据
    """
    distribution = WarningRepository.get_type_distribution()
    
    return jsonify(distribution)


@warning_bp.route('/api/warning/by-level/<int:level>')
def get_students_by_level(level):
    """
    获取指定等级的预警学生
    
    Args:
        level: 预警等级(0-3)
        
    Query Parameters:
        limit: 返回数量（可选）
        
    Returns:
        学生列表
    """
    limit = request.args.get('limit', default=50, type=int)
    
    students = WarningRepository.get_by_level(level, limit=limit)
    
    return jsonify(students)


@warning_bp.route('/api/warning/refresh', methods=['POST'])
def refresh_warnings():
    """
    刷新预警数据（重新分析）
    
    Returns:
        刷新结果
    """
    engine = WarningEngine()
    result = engine.refresh_warnings()
    
    return jsonify(result)
