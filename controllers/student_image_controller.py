"""Protected, class-scoped routes for the student image library."""

from pathlib import Path
from typing import Callable

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    Response,
    send_file,
)

from repositories import StudentImageRepository
from services.class_context import get_active_class_id, require_active_class
from services.student_image_service import ImageProcessingError, StudentImageService


student_image_bp = Blueprint('student_image', __name__)

VALID_MATCH_STATUSES = frozenset({'matched', 'pending', 'conflict'})


def _error_response(
    code: str, message: str, status_code: int
) -> tuple[Response, int]:
    """Build the stable JSON error shape used by image-library APIs."""
    return jsonify({'error': {'code': code, 'message': message}}), status_code


def _service_error_response(error: ImageProcessingError) -> tuple[Response, int]:
    """Translate user-correctable service failures into HTTP responses."""
    if error.code in {'not_found', 'student_not_found'}:
        status_code = 404
    elif error.code == 'binding_conflict':
        status_code = 409
    else:
        status_code = 400
    return _error_response(error.code, error.message, status_code)


def _run_service(class_id: int, operation: Callable[[], object]) -> object:
    """Run a service operation with consistent safe error translation."""
    try:
        return operation()
    except ImageProcessingError as error:
        return _service_error_response(error)
    except Exception:
        current_app.logger.exception(
            'Student image request failed for class %s', class_id
        )
        return _error_response(
            'request_failed', 'Student image request failed', 500
        )


def _confirmation_value(value: object) -> bool:
    """Interpret JSON booleans and conventional form boolean values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return False


def _private_file_response(path: Path, mimetype: str) -> Response:
    """Send a conditionally cacheable file without allowing shared caching."""
    response = send_file(
        path,
        mimetype=mimetype,
        conditional=True,
        max_age=3600,
    )
    response.headers['Cache-Control'] = 'private, max-age=3600'
    return response


@student_image_bp.get('/student-images')
@require_active_class
def index() -> object:
    """Render the current class's student image library page."""
    return render_template('student_image/index.html')


@student_image_bp.get('/api/student-images')
@require_active_class
def list_images() -> object:
    """Return one filtered page of image metadata for the active class."""
    class_id = get_active_class_id()
    status = request.args.get('status')
    if status is not None and status not in VALID_MATCH_STATUSES:
        return jsonify({
            'error': {
                'code': 'invalid_status',
                'message': 'Unknown student image status',
            }
        }), 400

    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 24, type=int), 1), 100)
    result = _run_service(
        class_id,
        lambda: StudentImageRepository.list_page(
            class_id,
            status,
            request.args.get('keyword', '').strip(),
            page,
            per_page,
        ),
    )
    if isinstance(result, tuple):
        return result
    return jsonify({
        'items': [item.to_dict() for item in result.items],
        'page': result.page,
        'per_page': result.per_page,
        'total': result.total,
        'pages': result.pages,
    })


@student_image_bp.post('/api/student-images/batch')
@require_active_class
def batch_upload() -> object:
    """Process repeated ``files`` fields, including a supported ZIP archive."""
    class_id = get_active_class_id()
    files = [file for file in request.files.getlist('files') if file.filename]
    if not files:
        return _error_response(
            'files_required', 'At least one image or ZIP file is required', 400
        )

    result = _run_service(
        class_id, lambda: StudentImageService.process_batch(class_id, files)
    )
    if isinstance(result, tuple):
        return result
    return jsonify(result)


@student_image_bp.post('/api/student-images/<int:image_id>/bind')
@require_active_class
def bind_image(image_id: int) -> object:
    """Bind or explicitly replace an active-class student's portrait."""
    class_id = get_active_class_id()
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form
    student_id = payload.get('student_id')
    if isinstance(student_id, bool):
        student_id = None
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return _error_response(
            'student_id_required', 'A valid student_id is required', 400
        )
    if student_id < 1:
        return _error_response(
            'student_id_required', 'A valid student_id is required', 400
        )

    result = _run_service(
        class_id,
        lambda: StudentImageService.bind_image(
            class_id,
            image_id,
            student_id,
            confirm_replace=_confirmation_value(payload.get('confirm_replace')),
        ),
    )
    if isinstance(result, tuple):
        return result
    return jsonify(result)


@student_image_bp.delete('/api/student-images/<int:image_id>')
@require_active_class
def delete_image(image_id: int) -> object:
    """Delete one image that belongs to the active class."""
    class_id = get_active_class_id()
    result = _run_service(
        class_id, lambda: StudentImageService.delete_image(class_id, image_id)
    )
    if isinstance(result, tuple):
        return result
    if result is False:
        return _error_response('not_found', 'Student image not found', 404)
    return jsonify({'success': True})


@student_image_bp.post('/api/student/<int:student_id>/image')
@require_active_class
def upload_student_image(student_id: int) -> object:
    """Upload and immediately bind one portrait to an active-class student."""
    class_id = get_active_class_id()
    file = request.files.get('file')
    if file is None or not file.filename:
        return _error_response('file_required', 'An image file is required', 400)

    result = _run_service(
        class_id,
        lambda: StudentImageService.process_upload(
            class_id,
            file,
            preferred_student_id=student_id,
            confirm_replace=_confirmation_value(
                request.form.get('confirm_replace')
            ),
        ),
    )
    if isinstance(result, tuple):
        return result
    return jsonify(result)


@student_image_bp.get('/media/student-images/<int:image_id>')
@require_active_class
def student_image_media(image_id: int) -> object:
    """Deliver private image bytes only after resolving the active-class row."""
    class_id = get_active_class_id()
    try:
        image = StudentImageRepository.get_by_id(image_id, class_id)
        if image is None:
            return _error_response('not_found', 'Student image not found', 404)

        path = StudentImageService.get_storage_path(image)
        if path.is_file():
            return _private_file_response(path, 'image/jpeg')

        current_app.logger.error(
            'Student image file missing for record %s', image.id
        )
        fallback = Path(current_app.static_folder) / 'img' / 'default-avatar.svg'
        return _private_file_response(fallback, 'image/svg+xml')
    except ImageProcessingError as error:
        return _service_error_response(error)
    except Exception:
        current_app.logger.exception(
            'Student image request failed for class %s', class_id
        )
        return _error_response(
            'request_failed', 'Student image request failed', 500
        )
