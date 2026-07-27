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
from flask import Blueprint, render_template, jsonify, request, current_app, session
from werkzeug.utils import secure_filename
from pathlib import Path
from uuid import uuid4

from models import (
    ImportRecord,
    ClassInfo,
)
from services.importers import (
    RainClassImporter,
    RainClassSummaryImporter,
    RainClassKnowledgeDetailImporter,
    RainClassKnowledgePointSummaryImporter,
    EducoderImporter,
    EducoderActivityImporter,
)
from services.importers.base_importer import (
    AuditPersistenceError,
    calculate_file_hash,
    record_failed_import,
)
from services.importers.parser_utils import detect_file_type, extract_class_info_from_filename
from services.analysis import BehaviorAnalyzer, KnowledgeAnalyzer, PracticeAnalyzer, WarningEngine
from services.class_context import get_active_class_id, require_active_class

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


def _get_target_class(payload) -> tuple[ClassInfo, object]:
    """Resolve an explicit active target class from form or JSON data."""
    raw_class_id = payload.get('class_id')
    try:
        class_id = int(raw_class_id)
    except (TypeError, ValueError):
        return None, (jsonify({
            'error': 'invalid_target_class',
            'message': '请选择有效的目标班级',
        }), 400)

    active_class_id = get_active_class_id()
    if class_id != active_class_id:
        return None, (jsonify({
            'error': 'class_context_mismatch',
            'message': '目标班级与当前活动班级不一致，请先切换班级',
            'active_class_id': active_class_id,
            'requested_class_id': class_id,
        }), 409)

    target = ClassInfo.query.filter_by(id=class_id, status='active').first()
    if target is None:
        return None, (jsonify({
            'error': 'invalid_target_class',
            'message': '目标班级不存在或已归档',
        }), 400)
    return target, None


def _class_mismatch(filename: str, target_class: ClassInfo):
    detected = extract_class_info_from_filename(filename)
    detected_name = (detected.get('class_name') or '').strip()
    if detected_name and detected_name != target_class.class_name.strip():
        return {
            'error': 'class_name_mismatch',
            'message': '文件名中的班级与目标班级不一致',
            'selected_class': target_class.class_name,
            'detected_class': detected_name,
        }
    return None


@import_bp.route('/import')
@require_active_class
def import_page():
    """数据导入页面"""
    class_id = get_active_class_id()
    classes = ClassInfo.query.filter_by(status='active').order_by(ClassInfo.class_name).all()
    requested_id = request.args.get('class_id', type=int)
    selected_id = requested_id if any(item.id == requested_id for item in classes) else class_id
    if selected_id != class_id:
        session['active_class_id'] = selected_id
    return render_template(
        'import/index.html',
        classes=classes,
        selected_class_id=selected_id,
    )


@import_bp.route('/api/import/upload', methods=['POST'])
@require_active_class
def upload_file():
    """
    上传并导入数据文件
    
    Returns:
        导入结果
    """
    target_class, error_response = _get_target_class(request.form)
    if error_response:
        return error_response
    files = [file for file in request.files.getlist('file') if file.filename]
    if not files:
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    unsupported_files = [file.filename for file in files if not allowed_file(file.filename)]
    if unsupported_files:
        if len(files) == 1:
            return jsonify({'success': False, 'message': '不支持的文件格式'}), 400
        return jsonify({'success': False, 'message': '存在不支持的文件格式', 'unsupported_files': unsupported_files}), 400

    mismatches = [(file.filename, _class_mismatch(file.filename, target_class)) for file in files]
    mismatches = [(name, mismatch) for name, mismatch in mismatches if mismatch]
    if mismatches and request.form.get('confirm_class_mismatch') != 'true':
        payload = dict(mismatches[0][1])
        if len(files) > 1:
            payload['conflicting_files'] = [name for name, _ in mismatches]
        return jsonify(payload), 409

    import_type = request.form.get('type', '').strip()
    results = []
    for file in files:
        try:
            results.append(_import_uploaded_file(file, target_class, import_type))
        except Exception as exc:
            if len(files) == 1:
                return jsonify({'success': False, 'message': str(exc)}), 500
            results.append({'filename': file.filename, 'success': False, 'message': str(exc), 'errors': [str(exc)], 'warnings': [], 'imported_count': 0})

    response = results[0] if len(files) == 1 else _build_batch_upload_response(results)
    if len(files) == 1:
        response.pop('filename', None)
    if any(item.get('success') for item in results):
        try:
            analysis_result = run_all_analysis(target_class.id)
            response['analysis'] = analysis_result
            if analysis_result.get('summary', {}).get('success') is False:
                response['analysis_warning'] = '数据导入成功，但自动分析未全部完成，请稍后重新分析'
        except Exception as exc:
            response['analysis_warning'] = f'自动分析失败: {exc}'
    return jsonify(response)


def _import_uploaded_file(file, target_class, import_type):
    original_filename = file.filename
    filename = secure_filename(original_filename)
    if not filename or len(filename) < 5:
        ext = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else 'xls'
        filename = f'upload_{uuid4().hex}.{ext}'
    upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)
    file_path = upload_folder / f'{uuid4().hex}_{filename}'
    file.save(file_path)
    result = import_data(str(file_path), target_class.id, session['admin_username'], import_type=import_type, original_filename=original_filename, file_hash=calculate_file_hash(file_path))
    result['filename'] = original_filename
    return result


def _build_batch_upload_response(results):
    imported_files = sum(bool(item.get('success')) for item in results)
    failed_files = len(results) - imported_files
    return {'success': failed_files == 0, 'partial_success': imported_files > 0 and failed_files > 0, 'message': f'共处理 {len(results)} 个文件，成功 {imported_files} 个，失败 {failed_files} 个', 'total_files': len(results), 'imported_files': imported_files, 'failed_files': failed_files, 'total_imported_rows': sum((item.get('imported_count', 0) or 0) for item in results if item.get('success')), 'results': results}


@import_bp.route('/api/import/folder', methods=['POST'])
@require_active_class
def import_folder():
    """
    一键导入指定文件夹中的所有Excel文件。

    Body:
        folder: 文件夹路径；支持相对项目根目录的路径，默认 new-datas。

    Returns:
        批量导入结果
    """
    payload = request.get_json(silent=True) or request.form
    target_class, error_response = _get_target_class(payload)
    if error_response:
        return error_response
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
        mismatch = _class_mismatch(file_path.name, target_class)
        if mismatch and str(payload.get('confirm_class_mismatch', '')).lower() != 'true':
            result = {
                **mismatch,
                'success': False,
                'pending_confirmation': True,
                'errors': [mismatch['message']],
                'warnings': [],
                'imported_count': 0,
            }
            result['filename'] = file_path.name
            results.append(result)
            failed_files += 1
            continue

        try:
            result = import_data(
                str(file_path),
                target_class.id,
                session['admin_username'],
                original_filename=file_path.name,
                file_hash=calculate_file_hash(file_path),
            )
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

    if imported_files:
        try:
            response['analysis'] = run_all_analysis(target_class.id)
        except Exception as e:
            response['analysis_warning'] = f'自动分析失败: {e}'

    return jsonify(response)


def import_data(file_path: str, class_id: int, uploaded_by: str,
                import_type: str = '', original_filename: str = '',
                file_hash: str = None) -> dict:
    """
    导入数据
    
    Args:
        file_path: 文件路径
        class_id: 用户明确选择的目标班级
        uploaded_by: 执行导入的管理员
        import_type: 导入类型（可选，自动检测）
        original_filename: 原始文件名（用于类型检测）
        
    Returns:
        导入结果
    """
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
            importer = RainClassKnowledgePointSummaryImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '雨课堂-知识点汇总'
        elif '学生汇总' in filename or '按学生汇总' in filename or '汇总' in filename:
            importer = RainClassSummaryImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '雨课堂-学生汇总'
        elif '知识图谱' in filename or '明细' in filename:
            importer = RainClassKnowledgeDetailImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '雨课堂-知识图谱明细'
        else:
            importer = RainClassImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '雨课堂'
    
    # 头歌系列
    elif import_type == '头歌' or '头歌' in filename or 'educoder' in filename:
        if '活跃度' in filename:
            importer = EducoderActivityImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '头歌-活跃度'
        elif '作业成绩' in filename:
            from services.importers.educoder_importer import EducoderAssignmentImporter
            importer = EducoderAssignmentImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '头歌-作业成绩'
        else:
            importer = EducoderImporter(
                file_path, class_id, uploaded_by, original_filename, file_hash
            )
            import_type = '头歌'
    
    else:
        error_message = f'无法识别文件类型: {import_type}'
        audit_error = None
        try:
            record_failed_import(
                class_id=class_id,
                filename=original_filename or Path(file_path).name,
                file_hash=file_hash or calculate_file_hash(Path(file_path)),
                uploaded_by=uploaded_by,
                import_type=import_type or '未知',
                error_message=error_message,
            )
        except AuditPersistenceError as exc:
            audit_error = str(exc)
        return {
            'success': False,
            'message': error_message if audit_error is None else f'{error_message}；{audit_error}',
            'errors': [
                '请手动指定导入类型或检查文件格式',
                *([audit_error] if audit_error else []),
            ],
            'class_id': class_id,
            'import_type': import_type or '未知',
        }
    
    # 执行导入
    result = importer.execute()
    result['import_type'] = import_type
    result['class_id'] = importer.class_id
    
    return result


@import_bp.route('/api/import/records')
@require_active_class
def get_import_records():
    """
    获取导入日志
    
    Query Parameters:
        limit: 返回数量（可选）
        
    Returns:
        导入记录列表
    """
    class_id = get_active_class_id()
    limit = request.args.get('limit', default=20, type=int)
    
    records = ImportRecord.get_recent_records(class_id, limit)
    
    return jsonify([r.to_dict() for r in records])


@import_bp.route('/api/import/analyze', methods=['POST'])
@require_active_class
def run_analysis():
    """
    一键重新分析所有数据
    
    Returns:
        分析结果
    """
    class_id = get_active_class_id()
    try:
        results = run_all_analysis(class_id)
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


def run_all_analysis(class_id: int) -> dict:
    """
    执行全量分析（内部函数，供自动分析和手动分析共用）
    
    每个分析器独立运行，单个失败不影响其他分析器。
    
    Returns:
        分析结果字典
    """
    analyzers = {
        'behavior': BehaviorAnalyzer(class_id),
        'practice': PracticeAnalyzer(class_id),
        'knowledge': KnowledgeAnalyzer(class_id),
        'warning': WarningEngine(class_id),
    }
    results = {}
    for name, analyzer in analyzers.items():
        try:
            results[name] = analyzer.analyze_all()
        except Exception as exc:
            results[name] = {'success': False, 'message': str(exc)}
    
    # 汇总统计
    analyzed_count = sum(
        item.get('analyzed_count', 0)
        for item in results.values()
        if item.get('success', True)
    )
    results['summary'] = {
        'success': all(item.get('success', True) for item in results.values()),
        'total_analyzed': analyzed_count,
        'message': f'班级 {class_id} 共分析 {analyzed_count} 条数据',
    }
    
    return results


@import_bp.route('/api/import/types')
@require_active_class
def get_import_types():
    """
    获取支持的导入类型
    
    Returns:
        导入类型列表
    """
    class_id = get_active_class_id()
    return jsonify([
        {'type': '雨课堂', 'description': '学习过程数据（到课率、视频完成率等）'},
        {'type': '雨课堂-学生汇总', 'description': '学生汇总表（知识点掌握率、完成率）'},
        {'type': '雨课堂-知识图谱明细', 'description': '知识图谱学习数据明细表'},
        {'type': '雨课堂-知识点汇总', 'description': '按知识点汇总表（掌握率、完成率、正确率）'},
        {'type': '头歌', 'description': '总成绩'},
        {'type': '头歌-活跃度', 'description': '课堂活跃度统计'},
        {'type': '头歌-作业成绩', 'description': '作业成绩表'}
    ])
