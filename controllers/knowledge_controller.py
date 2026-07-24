# -*- coding: utf-8 -*-
"""
知识点控制器

知识点分析页面，包括：
- 知识点掌握率排行
- 热力图
- 学生排名
- 风险学生列表
"""
from flask import Blueprint, render_template, jsonify, request
from repositories import KnowledgeRepository

knowledge_bp = Blueprint('knowledge', __name__)


@knowledge_bp.route('/knowledge')
def knowledge_page():
    """知识点分析页面"""
    return render_template('knowledge/index.html')


@knowledge_bp.route('/api/knowledge/list')
def get_knowledge_list():
    """
    获取知识点列表
    
    Returns:
        知识点列表
    """
    knowledge_names = KnowledgeRepository.get_all_knowledge_names()
    
    return jsonify(knowledge_names)


@knowledge_bp.route('/api/knowledge/statistics')
def get_knowledge_statistics():
    """
    获取知识点统计数据
    
    Returns:
        知识点统计列表
    """
    stats = KnowledgeRepository.get_knowledge_statistics()
    
    return jsonify(stats)


@knowledge_bp.route('/api/knowledge/point-summary')
def get_knowledge_point_summary():
    """
    获取雨课堂按知识点汇总数据。

    Query Parameters:
        limit: 返回数量（可选）

    Returns:
        知识点汇总列表
    """
    limit = request.args.get('limit', type=int)
    stats = KnowledgeRepository.get_point_summary_statistics(limit=limit)

    return jsonify(stats)


@knowledge_bp.route('/api/knowledge/students')
def get_students_by_knowledge_query():
    """
    按查询参数获取指定知识点掌握情况的学生列表。

    Query Parameters:
        knowledge_name: 知识点名称
        min_rate: 最低掌握率（可选）
        max_rate: 最高掌握率（可选）
        limit: 返回数量（可选）
    """
    knowledge_name = request.args.get('knowledge_name', '').strip()
    if not knowledge_name:
        return jsonify({'error': '缺少 knowledge_name 参数'}), 400

    min_rate = request.args.get('min_rate', type=float)
    max_rate = request.args.get('max_rate', type=float)
    limit = request.args.get('limit', default=50, type=int)

    students = KnowledgeRepository.get_students_by_knowledge(
        knowledge_name,
        min_rate=min_rate,
        max_rate=max_rate,
        limit=limit
    )

    return jsonify(students)


@knowledge_bp.route('/api/knowledge/<knowledge_name>/students')
def get_students_by_knowledge(knowledge_name):
    """
    获取指定知识点掌握情况的学生列表
    
    Args:
        knowledge_name: 知识点名称
        
    Query Parameters:
        min_rate: 最低掌握率（可选）
        max_rate: 最高掌握率（可选）
        limit: 返回数量（可选）
        
    Returns:
        学生列表
    """
    min_rate = request.args.get('min_rate', type=float)
    max_rate = request.args.get('max_rate', type=float)
    limit = request.args.get('limit', default=50, type=int)
    
    students = KnowledgeRepository.get_students_by_knowledge(
        knowledge_name,
        min_rate=min_rate,
        max_rate=max_rate,
        limit=limit
    )
    
    return jsonify(students)


@knowledge_bp.route('/api/knowledge/heatmap')
def get_knowledge_heatmap():
    """
    获取知识点热力图数据
    
    Query Parameters:
        class_id: 班级ID（可选）
        knowledge_limit: 知识点数量限制（可选）
        student_limit: 学生数量限制（可选）
        
    Returns:
        热力图数据
    """
    class_id = request.args.get('class_id', type=int)
    knowledge_limit = request.args.get('knowledge_limit', default=20, type=int)
    student_limit = request.args.get('student_limit', default=50, type=int)
    
    heatmap_data = KnowledgeRepository.get_heatmap_data(
        class_id=class_id,
        knowledge_limit=knowledge_limit,
        student_limit=student_limit
    )
    
    return jsonify(heatmap_data)


@knowledge_bp.route('/api/knowledge/weak-points')
def get_weak_knowledge_points():
    """
    获取整体薄弱知识点
    
    Query Parameters:
        threshold: 掌握率阈值（可选）
        
    Returns:
        薄弱知识点列表
    """
    threshold = request.args.get('threshold', default=40.0, type=float)
    
    weak_points = KnowledgeRepository.get_weak_knowledge_points(threshold)
    
    stats = KnowledgeRepository.get_knowledge_statistics()
    weak_stats = [s for s in stats if s['knowledge_name'] in weak_points]
    
    return jsonify(weak_stats)
