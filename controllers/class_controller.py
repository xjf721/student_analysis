from flask import Blueprint, jsonify, render_template, request, session, url_for

from models import ClassInfo, db
from repositories import ClassRepository
from services.class_comparison import ClassComparisonService, ClassNotFoundError


classes_bp = Blueprint('classes', __name__)
MAX_CLASS_ID = 2_147_483_647


def _payload():
    data = request.get_json(silent=True)
    return data if data is not None else request.form.to_dict()


def _class_data(item):
    data = item.to_dict()
    data.update(ClassRepository.get_overview(item.id))
    return data


@classes_bp.get('/classes')
def index():
    classes = ClassRepository.get_all()
    return render_template(
        'class/index.html',
        classes=[{'item': item, 'overview': ClassRepository.get_overview(item.id)} for item in classes],
    )


@classes_bp.get('/class-compare')
def compare_page():
    return render_template('class/compare.html', classes=ClassRepository.get_all())


@classes_bp.get('/api/classes/compare')
def compare_classes():
    raw_class_ids = request.args.getlist('class_id')
    class_ids = []
    seen = set()
    for raw_class_id in raw_class_ids:
        if (
            len(raw_class_id) > 10
            or not raw_class_id.isascii()
            or not raw_class_id.isdecimal()
        ):
            return jsonify({'error': 'invalid_class_id'}), 400
        class_id = int(raw_class_id)
        if class_id < 1 or class_id > MAX_CLASS_ID:
            return jsonify({'error': 'invalid_class_id'}), 400
        if class_id not in seen:
            seen.add(class_id)
            class_ids.append(class_id)
    try:
        return jsonify(ClassComparisonService.compare(class_ids))
    except ClassNotFoundError as error:
        return jsonify({'error': 'class_not_found', 'class_id': error.class_id}), 400
    except ValueError:
        return jsonify({'error': 'at_least_two_distinct_classes_required'}), 400


@classes_bp.get('/classes/<int:class_id>')
def detail(class_id):
    item = ClassRepository.get_by_id(class_id)
    if item is None:
        return render_template('errors/404.html'), 404
    if item.status == 'active':
        session['active_class_id'] = item.id
    return render_template(
        'class/detail.html',
        class_item=item,
        overview=ClassRepository.get_overview(class_id),
        recent_imports=ClassRepository.get_recent_imports(class_id),
    )


@classes_bp.get('/api/classes')
def list_classes():
    return jsonify([_class_data(item) for item in ClassRepository.get_all()])


@classes_bp.post('/api/classes')
def create_class():
    data = _payload()
    if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
        return jsonify({'error': 'invalid_class_payload'}), 400
    if not (data.get('class_name') or '').strip():
        return jsonify({'error': 'class_name_required'}), 400
    item = ClassRepository.create(data)
    return jsonify(_class_data(item)), 201


@classes_bp.patch('/api/classes/<int:class_id>')
def update_class(class_id):
    item = ClassRepository.get_by_id(class_id)
    if item is None:
        return jsonify({'error': 'class_not_found'}), 404
    data = _payload()
    if not isinstance(data, dict) or any(not isinstance(value, str) for value in data.values()):
        return jsonify({'error': 'invalid_class_payload'}), 400
    if 'class_name' in data:
        class_name = (data.get('class_name') or '').strip()
        if not class_name:
            return jsonify({'error': 'class_name_required'}), 400
        item.class_name = class_name
    for field in ('teacher_name', 'term', 'notes'):
        if field in data:
            setattr(item, field, (data.get(field) or '').strip() or None)
    db.session.commit()
    return jsonify(_class_data(item))


@classes_bp.post('/api/classes/<int:class_id>/select')
def select_class(class_id):
    item = ClassInfo.query.filter_by(id=class_id, status='active').first_or_404()
    session['active_class_id'] = item.id
    return jsonify({'success': True, 'redirect': url_for('dashboard.index')})


@classes_bp.post('/api/classes/<int:class_id>/archive')
def archive_class(class_id):
    item = ClassRepository.get_by_id(class_id)
    if item is None:
        return jsonify({'error': 'class_not_found'}), 404
    item.status = 'archived'
    db.session.commit()
    if session.get('active_class_id') == item.id:
        session.pop('active_class_id', None)
    return jsonify(_class_data(item))


@classes_bp.post('/api/classes/<int:class_id>/restore')
def restore_class(class_id):
    item = ClassRepository.get_by_id(class_id)
    if item is None:
        return jsonify({'error': 'class_not_found'}), 404
    item.status = 'active'
    db.session.commit()
    return jsonify(_class_data(item))


@classes_bp.delete('/api/classes/<int:class_id>')
def delete_class(class_id):
    item = ClassRepository.get_by_id(class_id)
    if item is None:
        return jsonify({'error': 'class_not_found'}), 404
    if not ClassRepository.delete_empty(item):
        return jsonify({'error': 'class_has_data'}), 409
    if session.get('active_class_id') == class_id:
        session.pop('active_class_id', None)
    return jsonify({'success': True})
