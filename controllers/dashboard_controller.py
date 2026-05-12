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

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    """首页"""
    return render_template('dashboard/index.html')


@dashboard_bp.route('/api/debug/stats')
def debug_stats():
    """诊断：直接查数据库原始值"""
    from models import db, Student, StudentBehavior, StudentPractice, StudentKnowledgeMastery, WarningRecord
    from sqlalchemy import func
    from flask import current_app
    
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', 'unknown')
    # 隐藏密码
    if '@' in db_uri:
        db_uri = db_uri.split('@')[0].split('://')[0] + '://***@' + db_uri.split('@')[1]
    
    student_count = db.session.query(func.count(Student.id)).scalar() or 0
    beh_count = db.session.query(func.count(StudentBehavior.id)).scalar() or 0
    prac_count = db.session.query(func.count(StudentPractice.id)).scalar() or 0
    kp_count = db.session.query(func.count(StudentKnowledgeMastery.id)).scalar() or 0
    warn_count = db.session.query(func.count(WarningRecord.id)).scalar() or 0
    
    return jsonify({
        'database': db_uri,
        'student_count': student_count,
        'behavior_count': beh_count,
        'practice_count': prac_count,
        'knowledge_count': kp_count,
        'warning_count': warn_count,
        'student_sample': [{'student_no': s.student_no, 'name': s.name} 
                          for s in db.session.query(Student).limit(3).all()],
        'behavior_sample': [{'student_id': b.student_id, 'attendance_rate': b.attendance_rate}
                           for b in db.session.query(StudentBehavior).limit(3).all()]
    })


@dashboard_bp.route('/api/stats')
def get_stats():
    """
    获取首页统计数据
    
    Returns:
        JSON格式的统计数据
    """
    # 学生总数
    total_students = StudentRepository.get_count()
    
    # 行为统计
    behavior_stats = BehaviorRepository.get_statistics()
    
    # 预警统计
    warning_stats = WarningRepository.get_statistics()
    
    # 知识点统计
    knowledge_stats = KnowledgeRepository.get_knowledge_statistics()
    weak_knowledge_count = len([k for k in knowledge_stats if k['avg_mastery_rate'] < 40])
    
    return jsonify({
        'total_students': total_students,
        'avg_attendance_rate': behavior_stats['avg_attendance_rate'],
        'avg_behavior_score': behavior_stats['avg_behavior_score'],
        'warning_count': warning_stats['total_warnings'],
        'high_risk_count': warning_stats['by_level'].get('高危', 0),
        'weak_knowledge_count': weak_knowledge_count
    })


@dashboard_bp.route('/api/radar')
def get_radar_data():
    """
    获取班级画像雷达图数据
    
    Returns:
        雷达图数据
    """
    analyzer = BehaviorAnalyzer()
    radar_data = analyzer.get_radar_data()
    
    return jsonify(radar_data)


@dashboard_bp.route('/api/warning-ranking')
def get_warning_ranking():
    """
    获取风险学生排行
    
    Returns:
        风险学生列表
    """
    high_risk_students = WarningRepository.get_high_risk_students(min_score=60, limit=10)
    
    return jsonify(high_risk_students)


@dashboard_bp.route('/api/heatmap')
def get_heatmap():
    """
    获取知识点热力图数据
    
    Returns:
        热力图数据
    """
    heatmap_data = KnowledgeRepository.get_heatmap_data(
        knowledge_limit=15,
        student_limit=30
    )
    
    return jsonify(heatmap_data)


@dashboard_bp.route('/api/knowledge-ranking')
def get_knowledge_ranking():
    """
    获取知识点掌握率排行
    
    Returns:
        知识点排行数据
    """
    stats = KnowledgeRepository.get_knowledge_statistics()
    
    # 取前10个最薄弱的知识点
    weak_points = sorted(stats, key=lambda x: x['avg_mastery_rate'])[:10]
    
    return jsonify(weak_points)
