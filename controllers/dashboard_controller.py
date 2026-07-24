# -*- coding: utf-8 -*-
"""
Dashboard控制器

首页展示，包括：
- 指标卡片
- 班级画像雷达图
- 风险学生排行
- 知识点热力图
"""
from flask import Blueprint, render_template, jsonify
from repositories import StudentRepository, BehaviorRepository, KnowledgeRepository, WarningRepository
from services.analysis import BehaviorAnalyzer, KnowledgeAnalyzer
from services.class_context import get_active_class_id, require_active_class

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@require_active_class
def index():
    """首页"""
    class_id = get_active_class_id()
    return render_template('dashboard/index.html')


@dashboard_bp.route('/api/stats')
@require_active_class
def get_stats():
    """
    获取首页统计数据
    
    Returns:
        JSON格式的统计数据
    """
    class_id = get_active_class_id()
    # 学生总数
    total_students = StudentRepository.get_count(class_id)
    
    # 行为统计
    behavior_stats = BehaviorRepository.get_statistics(class_id)
    
    # 预警统计
    warning_stats = WarningRepository.get_statistics(class_id)
    
    # 知识点统计
    knowledge_stats = KnowledgeRepository.get_knowledge_statistics(class_id)
    weak_knowledge_count = len([k for k in knowledge_stats if k['avg_mastery_rate'] < 40])
    
    return jsonify({
        'total_students': total_students,
        'avg_attendance_rate': behavior_stats['avg_attendance_rate'],
        'avg_behavior_score': behavior_stats['avg_behavior_score'],
        'warning_count': warning_stats['warning_student_count'],
        'high_risk_count': warning_stats['by_level'].get('高危', 0),
        'weak_knowledge_count': weak_knowledge_count
    })


@dashboard_bp.route('/api/radar')
@require_active_class
def get_radar_data():
    """
    获取班级画像雷达图数据
    
    Returns:
        雷达图数据
    """
    class_id = get_active_class_id()
    student_count = StudentRepository.get_count(class_id)
    if not student_count:
        return jsonify({
            'student_count': 0,
            'indicator': [],
            'values': [],
        })

    analyzer = BehaviorAnalyzer(class_id)
    radar_data = analyzer.get_radar_data()
    radar_data['student_count'] = student_count
    
    return jsonify(radar_data)


@dashboard_bp.route('/api/warning-ranking')
@require_active_class
def get_warning_ranking():
    """
    获取风险学生排行
    
    Returns:
        风险学生列表
    """
    class_id = get_active_class_id()
    high_risk_students = WarningRepository.get_high_risk_students(class_id, min_score=60, limit=10)
    
    return jsonify(high_risk_students)


@dashboard_bp.route('/api/heatmap')
@require_active_class
def get_heatmap():
    """
    获取知识点热力图数据
    
    Returns:
        热力图数据
    """
    class_id = get_active_class_id()
    heatmap_data = KnowledgeRepository.get_heatmap_data(
        class_id,
        knowledge_limit=15,
        student_limit=30
    )
    
    return jsonify(heatmap_data)


@dashboard_bp.route('/api/knowledge-ranking')
@require_active_class
def get_knowledge_ranking():
    """
    获取知识点掌握率排行
    
    Returns:
        知识点排行数据
    """
    class_id = get_active_class_id()
    stats = KnowledgeRepository.get_knowledge_statistics(class_id)
    
    # 取前10个最薄弱的知识点
    weak_points = sorted(stats, key=lambda x: x['avg_mastery_rate'])[:10]
    
    return jsonify(weak_points)
