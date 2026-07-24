# -*- coding: utf-8 -*-
"""
学生控制器

学生画像页面，包括：
- 学生详情
- 学习行为雷达图
- 理论vs实践对比图
- 薄弱知识点列表
- 风险原因分析
"""
from flask import Blueprint, render_template, jsonify, request
from repositories import StudentRepository, KnowledgeRepository, WarningRepository
from services.analysis import KnowledgeAnalyzer, PracticeAnalyzer

student_bp = Blueprint('student', __name__)


@student_bp.route('/students')
def student_list():
    """学生列表页面"""
    return render_template('student/list.html')


@student_bp.route('/student/<int:student_id>')
def student_detail(student_id):
    """学生画像页面"""
    return render_template('student/detail.html', student_id=student_id)


@student_bp.route('/api/students')
def get_students():
    """
    获取学生列表
    
    Query Parameters:
        class_id: 班级ID（可选）
        keyword: 搜索关键词（可选）
        
    Returns:
        学生列表
    """
    class_id = request.args.get('class_id', type=int)
    keyword = request.args.get('keyword', '')
    
    if keyword:
        students = StudentRepository.search(keyword)
    else:
        students = StudentRepository.get_all(class_id)
    
    return jsonify([s.to_dict() for s in students])


@student_bp.route('/api/student/<int:student_id>')
def get_student_detail(student_id):
    """
    获取学生详细信息
    
    Args:
        student_id: 学生ID
        
    Returns:
        学生详情
    """
    student_detail = StudentRepository.get_with_details(student_id)
    
    if not student_detail:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(student_detail)


@student_bp.route('/api/student/<int:student_id>/radar')
def get_student_radar(student_id):
    """
    获取学生学习行为雷达图数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        雷达图数据
    """
    student = StudentRepository.get_by_id(student_id)
    
    if not student or not student.behavior:
        return jsonify({
            'indicator': [],
            'values': []
        })
    
    behavior = student.behavior
    
    return jsonify({
        'indicator': [
            {'name': '到课率', 'max': 100},
            {'name': '视频完成率', 'max': 100},
            {'name': '作业提交率', 'max': 100},
            {'name': '作业得分率', 'max': 100},
            {'name': 'PPT查看率', 'max': 100}
        ],
        'values': [
            behavior.attendance_rate,
            behavior.video_finish_rate,
            behavior.exercise_submit_rate,
            behavior.exercise_score_rate,
            behavior.ppt_view_rate
        ]
    })


@student_bp.route('/api/student/<int:student_id>/weak-points')
def get_student_weak_points(student_id):
    """
    获取学生薄弱知识点
    
    Args:
        student_id: 学生ID
        
    Returns:
        薄弱知识点列表
    """
    analyzer = KnowledgeAnalyzer()
    weak_points = analyzer.get_student_weak_points(student_id, threshold=60)
    
    return jsonify(weak_points)


@student_bp.route('/api/student/<int:student_id>/theory-practice')
def get_theory_practice_comparison(student_id):
    """
    获取学生理论与实践对比数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        对比数据
    """
    student = StudentRepository.get_by_id(student_id)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(StudentRepository.get_theory_practice(student_id))


@student_bp.route('/api/student/<int:student_id>/class-comparison')
def get_class_comparison(student_id):
    """
    获取学生与班级平均对比数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        对比数据
    """
    analyzer = KnowledgeAnalyzer()
    comparison_data = analyzer.compare_with_class_avg(student_id)
    
    return jsonify(comparison_data)


@student_bp.route('/student/<int:student_id>/overview')
def student_overview(student_id):
    """学生数据全览页面"""
    return render_template('student/overview.html', student_id=student_id)


@student_bp.route('/api/student/<int:student_id>/overview')
def get_student_overview(student_id):
    """
    获取学生全览聚合数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        全览数据JSON
    """
    overview_data = StudentRepository.get_full_overview(student_id)
    
    if not overview_data:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(overview_data)
