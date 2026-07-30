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
from flask import Blueprint, abort, current_app, render_template, jsonify, request
from repositories import StudentRepository, KnowledgeRepository, WarningRepository
from services.analysis import KnowledgeAnalyzer, PracticeAnalyzer
from services.class_context import get_active_class_id, require_active_class

student_bp = Blueprint('student', __name__)


@student_bp.route('/students')
@require_active_class
def student_list():
    """学生列表页面"""
    class_id = get_active_class_id()
    return render_template('student/list.html')


@student_bp.route('/student/<int:student_id>')
@require_active_class
def student_detail(student_id):
    """学生画像页面"""
    class_id = get_active_class_id()
    if not StudentRepository.get_by_id(student_id, class_id):
        abort(404)
    return render_template('student/detail.html', student_id=student_id)


@student_bp.route('/api/students')
@require_active_class
def get_students():
    """
    获取学生列表
    
    Query Parameters:
        class_id: 班级ID（可选）
        keyword: 搜索关键词（可选）
        
    Returns:
        学生列表
    """
    class_id = get_active_class_id()
    keyword = request.args.get('keyword', '').strip()
    
    if keyword:
        students = StudentRepository.search(keyword, class_id)
    else:
        students = StudentRepository.get_all(class_id)
    
    return jsonify([s.to_dict() for s in students])


@student_bp.route('/api/student/<int:student_id>')
@require_active_class
def get_student_detail(student_id):
    """
    获取学生详细信息
    
    Args:
        student_id: 学生ID
        
    Returns:
        学生详情
    """
    class_id = get_active_class_id()
    student_detail = StudentRepository.get_with_details(student_id, class_id)
    
    if not student_detail:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(student_detail)


@student_bp.route('/api/student/<int:student_id>/radar')
@require_active_class
def get_student_radar(student_id):
    """
    获取学生学习行为雷达图数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        雷达图数据
    """
    class_id = get_active_class_id()
    student = StudentRepository.get_by_id(student_id, class_id)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    if not student.behavior:
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
@require_active_class
def get_student_weak_points(student_id):
    """
    获取学生薄弱知识点
    
    Args:
        student_id: 学生ID
        
    Returns:
        薄弱知识点列表
    """
    class_id = get_active_class_id()
    if not StudentRepository.get_by_id(student_id, class_id):
        return jsonify({'error': '学生不存在'}), 404
    analyzer = KnowledgeAnalyzer(class_id)
    weak_points = analyzer.get_student_weak_points(student_id, threshold=60)
    
    return jsonify(weak_points)


@student_bp.route('/api/student/<int:student_id>/theory-practice')
@require_active_class
def get_theory_practice_comparison(student_id):
    """
    获取学生理论与实践对比数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        对比数据
    """
    class_id = get_active_class_id()
    student = StudentRepository.get_by_id(student_id, class_id)
    
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(StudentRepository.get_theory_practice(student_id, class_id))


@student_bp.route('/api/student/<int:student_id>/class-comparison')
@require_active_class
def get_class_comparison(student_id):
    """
    获取学生与班级平均对比数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        对比数据
    """
    class_id = get_active_class_id()
    if not StudentRepository.get_by_id(student_id, class_id):
        return jsonify({'error': '学生不存在'}), 404
    analyzer = KnowledgeAnalyzer(class_id)
    comparison_data = analyzer.compare_with_class_avg(student_id)
    
    return jsonify(comparison_data)


@student_bp.route('/student/<int:student_id>/overview')
@require_active_class
def student_overview(student_id):
    """学生数据全览页面"""
    class_id = get_active_class_id()
    if not StudentRepository.get_by_id(student_id, class_id):
        abort(404)
    return render_template('student/overview.html', student_id=student_id)


@student_bp.route('/api/student/<int:student_id>/overview')
@require_active_class
def get_student_overview(student_id):
    """
    获取学生全览聚合数据
    
    Args:
        student_id: 学生ID
        
    Returns:
        全览数据JSON
    """
    class_id = get_active_class_id()
    overview_data = StudentRepository.get_full_overview(student_id, class_id)
    
    if not overview_data:
        return jsonify({'error': '学生不存在'}), 404
    
    return jsonify(overview_data)


@student_bp.route('/api/student/<int:student_id>', methods=['DELETE'])
@require_active_class
def delete_student(student_id: int):
    """删除当前班级的一名学生及全部关联数据。"""
    class_id = get_active_class_id()
    try:
        student = StudentRepository.delete(student_id, class_id)
    except Exception:
        current_app.logger.exception(
            'Failed to delete student id=%s from class id=%s',
            student_id,
            class_id,
        )
        return jsonify({
            'error': 'student_delete_failed',
            'message': '删除学生失败，请稍后重试',
        }), 500

    if not student:
        return jsonify({
            'error': 'student_not_found',
            'message': '学生不存在或不属于当前班级',
        }), 404

    return jsonify({
        'message': f'已删除学生{student["name"]}（{student["student_no"]}）及其全部关联数据',
        'student': student,
    })
