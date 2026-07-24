# -*- coding: utf-8 -*-
"""
数据导入控制器

数据导入页面，包括：
- 文件上传
- 自动识别类型
- 数据校验
- 导入日志
- 一键重新分析
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from werkzeug.utils import secure_filename
from pathlib import Path

from models import (
    db,
    ImportRecord,
    Student,
    ClassInfo,
    StudentBehavior,
    StudentPractice,
    StudentAssignmentDetail,
    StudentAssignmentChallenge,
    StudentKnowledgeMastery,
    KnowledgePointSummary,
    WarningRecord,
)
from services.importers import (
    RainClassImporter,
    RainClassSummaryImporter,
    RainClassKnowledgeDetailImporter,
    RainClassKnowledgePointSummaryImporter,
    EducoderImporter,
    EducoderActivityImporter,
)
from services.importers.parser_utils import detect_file_type
from services.analysis import BehaviorAnalyzer, KnowledgeAnalyzer, PracticeAnalyzer, WarningEngine

import_bp = Blueprint('import', __name__)


def allowed_file(filename: str) -> bool:
    """检查文件类型是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS', {'xlsx', 'xls'})


def resolve_import_folder(folder: str) -> Path:
    """
    解析批量导入目录。

    相对路径以项目根目录为基准，便于直接填写 new-datas；绝对路径保持原样。
    """
    folder = (folder or 'new-datas').strip().strip('"').strip("'")
    folder_path = Path(folder).expanduser()
    if not folder_path.is_absolute():
        folder_path = Path(current_app.root_path) / folder_path
    return folder_path.resolve()


@import_bp.route('/import')
def import_page():
    """数据导入页面"""
    return render_template('import/index.html')


@import_bp.route('/api/import/upload', methods=['POST'])
def upload_file():
    """
    上传并导入数据文件
    
    Returns:
        导入结果
    """
    # 检查文件是否存在
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '不支持的文件格式'}), 400
    
    # 保存原始文件名（用于类型检测）
    original_filename = file.filename
    
    # 保存文件（使用安全的文件名）
    filename = secure_filename(file.filename)
    # 如果secure_filename处理后为空或太短，使用时间戳
    if not filename or len(filename) < 5:
        import time
        ext = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else 'xls'
        filename = f"upload_{int(time.time())}.{ext}"
    
    upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_folder / filename
    file.save(file_path)
    
    # 自动检测文件类型并选择导入器（使用原始文件名检测）
    import_type = request.form.get('type', '').strip()
    
    try:
        result = import_data(str(file_path), import_type, original_filename)
        
        # 导入成功后自动触发分析
        if result.get('success'):
            try:
                analysis_result = run_all_analysis()
                result['analysis'] = analysis_result
            except Exception as e:
                result['analysis_warning'] = f'自动分析失败: {e}'
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@import_bp.route('/api/import/folder', methods=['POST'])
def import_folder():
    """
    一键导入指定文件夹中的所有Excel文件。

    Body:
        folder: 文件夹路径；支持相对项目根目录的路径，默认 new-datas。

    Returns:
        批量导入结果
    """
    payload = request.get_json(silent=True) or request.form
    folder = payload.get('folder', 'new-datas')
    folder_path = resolve_import_folder(folder)

    if not folder_path.exists():
        return jsonify({
            'success': False,
            'message': f'文件夹不存在: {folder_path}'
        }), 400

    if not folder_path.is_dir():
        return jsonify({
            'success': False,
            'message': f'指定路径不是文件夹: {folder_path}'
        }), 400

    excel_files = sorted(
        [
            file_path for file_path in folder_path.iterdir()
            if file_path.is_file() and allowed_file(file_path.name)
        ],
        key=lambda p: p.name.lower()
    )

    if not excel_files:
        return jsonify({
            'success': False,
            'message': f'文件夹中没有可导入的Excel文件: {folder_path}',
            'folder': str(folder_path),
            'total_files': 0,
            'results': []
        }), 400

    results = []
    imported_files = 0
    failed_files = 0
    total_imported_rows = 0

    for file_path in excel_files:
        try:
            result = import_data(str(file_path), '', file_path.name)
        except Exception as e:
            result = {
                'success': False,
                'message': str(e),
                'errors': [str(e)],
                'warnings': [],
                'imported_count': 0
            }

        result['filename'] = file_path.name
        results.append(result)

        if result.get('success'):
            imported_files += 1
            total_imported_rows += result.get('imported_count', 0) or 0
        else:
            failed_files += 1

    response = {
        'success': failed_files == 0,
        'partial_success': imported_files > 0 and failed_files > 0,
        'message': f'共发现 {len(excel_files)} 个Excel文件，成功导入 {imported_files} 个，失败 {failed_files} 个',
        'folder': str(folder_path),
        'total_files': len(excel_files),
        'imported_files': imported_files,
        'failed_files': failed_files,
        'total_imported_rows': total_imported_rows,
        'results': results
    }

    if imported_files > 0:
        try:
            response['analysis'] = run_all_analysis()
        except Exception as e:
            response['analysis_warning'] = f'自动分析失败: {e}'

    return jsonify(response)


def import_data(file_path: str, import_type: str = '', original_filename: str = '') -> dict:
    """
    导入数据
    
    Args:
        file_path: 文件路径
        import_type: 导入类型（可选，自动检测）
        original_filename: 原始文件名（用于类型检测）
        
    Returns:
        导入结果
    """
    import pandas as pd
    
    # 使用原始文件名进行检测（保留中文）
    filename = original_filename.lower() if original_filename else Path(file_path).name.lower()
    
    # 优先通过文件名判断类型（更可靠）
    if not import_type:
        # 雨课堂系列
        if '雨课堂' in filename:
            if '按知识点汇总' in filename or ('知识点' in filename and '汇总' in filename and '学生' not in filename):
                import_type = '雨课堂-知识点汇总'
            elif '学生汇总' in filename or '按学生汇总' in filename or '汇总' in filename:
                import_type = '雨课堂-学生汇总'
            elif '知识图谱' in filename or '明细' in filename:
                import_type = '雨课堂-知识图谱明细'
            else:
                import_type = '雨课堂'
        # 头歌系列
        elif '头歌' in filename or 'educoder' in filename:
            if '活跃度' in filename:
                import_type = '头歌-活跃度'
            elif '作业成绩' in filename:
                import_type = '头歌-作业成绩'
            else:
                import_type = '头歌'
        else:
            # 尝试通过列名检测
            try:
                from services.importers.parser_utils import read_excel_smart
                df = read_excel_smart(file_path)
                import_type = detect_file_type(df, file_path) or '未知'
            except Exception:
                import_type = '未知'
    
    # 选择导入器
    importer = None
    
    # 雨课堂系列
    if import_type == '雨课堂' or '雨课堂' in filename:
        if import_type == '雨课堂-知识点汇总' or '按知识点汇总' in filename or ('知识点' in filename and '汇总' in filename and '学生' not in filename):
            importer = RainClassKnowledgePointSummaryImporter(file_path, display_filename=original_filename)
            import_type = '雨课堂-知识点汇总'
        elif '学生汇总' in filename or '按学生汇总' in filename or '汇总' in filename:
            importer = RainClassSummaryImporter(file_path, display_filename=original_filename)
            import_type = '雨课堂-学生汇总'
        elif '知识图谱' in filename or '明细' in filename:
            importer = RainClassKnowledgeDetailImporter(file_path, display_filename=original_filename)
            import_type = '雨课堂-知识图谱明细'
        else:
            importer = RainClassImporter(file_path, display_filename=original_filename)
            import_type = '雨课堂'
    
    # 头歌系列
    elif import_type == '头歌' or '头歌' in filename or 'educoder' in filename:
        if '活跃度' in filename:
            importer = EducoderActivityImporter(file_path, display_filename=original_filename)
            import_type = '头歌-活跃度'
        elif '作业成绩' in filename:
            from services.importers.educoder_importer import EducoderAssignmentImporter
            importer = EducoderAssignmentImporter(file_path, display_filename=original_filename)
            import_type = '头歌-作业成绩'
        else:
            importer = EducoderImporter(file_path, display_filename=original_filename)
            import_type = '头歌'
    
    else:
        return {
            'success': False,
            'message': f'无法识别文件类型: {import_type}',
            'errors': ['请手动指定导入类型或检查文件格式']
        }
    
    # 执行导入
    result = importer.execute()
    result['import_type'] = import_type
    
    return result


@import_bp.route('/api/import/records')
def get_import_records():
    """
    获取导入日志
    
    Query Parameters:
        limit: 返回数量（可选）
        
    Returns:
        导入记录列表
    """
    limit = request.args.get('limit', default=20, type=int)
    
    records = ImportRecord.get_recent_records(limit=limit)
    
    return jsonify([r.to_dict() for r in records])


@import_bp.route('/api/import/analyze', methods=['POST'])
def run_analysis():
    """
    一键重新分析所有数据
    
    Returns:
        分析结果
    """
    try:
        results = run_all_analysis()
        return jsonify({
            'success': True,
            'message': '分析完成',
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'分析失败: {str(e)}'
        }), 500


@import_bp.route('/api/import/clear-all', methods=['POST'])
def clear_all_data():
    """
    一键清空所有已导入和已分析的数据。

    仅清空数据库数据，不删除磁盘上的Excel原始文件。
    """
    try:
        delete_order = [
            WarningRecord,
            StudentAssignmentChallenge,
            StudentAssignmentDetail,
            StudentKnowledgeMastery,
            KnowledgePointSummary,
            StudentBehavior,
            StudentPractice,
            Student,
            ClassInfo,
            ImportRecord,
        ]
        counts = {}

        for model in delete_order:
            counts[model.__tablename__] = db.session.query(model).delete(synchronize_session=False)

        db.session.commit()

        total_deleted = sum(counts.values())
        return jsonify({
            'success': True,
            'message': f'已清空数据库数据，共删除 {total_deleted} 条记录',
            'counts': counts,
            'total_deleted': total_deleted
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'清空数据失败: {str(e)}'
        }), 500


def run_all_analysis() -> dict:
    """
    执行全量分析（内部函数，供自动分析和手动分析共用）
    
    每个分析器独立运行，单个失败不影响其他分析器。
    
    Returns:
        分析结果字典
    """
    results = {}
    
    # 1. 行为分析
    try:
        behavior_analyzer = BehaviorAnalyzer()
        results['behavior'] = behavior_analyzer.analyze_all()
    except Exception as e:
        results['behavior'] = {'success': False, 'message': str(e)}
    
    # 2. 实践分析
    try:
        practice_analyzer = PracticeAnalyzer()
        results['practice'] = practice_analyzer.analyze_all()
    except Exception as e:
        results['practice'] = {'success': False, 'message': str(e)}
    
    # 3. 知识点分析
    try:
        knowledge_analyzer = KnowledgeAnalyzer()
        results['knowledge'] = knowledge_analyzer.analyze_all()
    except Exception as e:
        results['knowledge'] = {'success': False, 'message': str(e)}
    
    # 4. 风险预警
    try:
        warning_engine = WarningEngine()
        results['warning'] = warning_engine.analyze_all()
    except Exception as e:
        results['warning'] = {'success': False, 'message': str(e)}
    
    # 汇总统计
    analyzed_count = sum(
        r.get('analyzed_count', 0) 
        for r in results.values() 
        if isinstance(r, dict) and r.get('success', True)
    )
    results['summary'] = {
        'success': True,
        'total_analyzed': analyzed_count,
        'message': f'共触发 {len(results)} 项分析，汇总分析 {analyzed_count} 条数据'
    }
    
    return results


@import_bp.route('/api/import/types')
def get_import_types():
    """
    获取支持的导入类型
    
    Returns:
        导入类型列表
    """
    return jsonify([
        {'type': '雨课堂', 'description': '学习过程数据（到课率、视频完成率等）'},
        {'type': '雨课堂-学生汇总', 'description': '学生汇总表（知识点掌握率、完成率）'},
        {'type': '雨课堂-知识图谱明细', 'description': '知识图谱学习数据明细表'},
        {'type': '雨课堂-知识点汇总', 'description': '按知识点汇总表（掌握率、完成率、正确率）'},
        {'type': '头歌', 'description': '总成绩'},
        {'type': '头歌-活跃度', 'description': '课堂活跃度统计'},
        {'type': '头歌-作业成绩', 'description': '作业成绩表'}
    ])
