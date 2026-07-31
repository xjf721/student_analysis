"""API coverage for the protected, class-scoped student image library."""

from io import BytesIO
import logging
import zipfile

from PIL import Image

from models import Student, StudentImage, db
from repositories import StudentImageRepository
from services.student_image_service import StudentImageService
from werkzeug.datastructures import FileStorage


def login_and_select(client, class_id: int) -> None:
    """Authenticate the test client and select one active class."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
    })
    client.post(f'/api/classes/{class_id}/select')


def add_student(class_id: int, student_no: str, name: str) -> Student:
    """Persist one student and return it with its generated identifier."""
    student = Student(student_no=student_no, name=name, class_id=class_id)
    db.session.add(student)
    db.session.commit()
    return student


def upload_image(class_id: int, filename: str, content: bytes) -> StudentImage:
    """Create a real normalized image through the production service."""
    result = StudentImageService.process_upload(
        class_id,
        FileStorage(stream=BytesIO(content), filename=filename),
    )
    return db.session.get(StudentImage, result['image']['id'])


def build_zip(filename: str, content: bytes) -> bytes:
    """Return an in-memory ZIP containing one image."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename, content)
    return buffer.getvalue()


def colored_jpeg(color: tuple[int, int, int]) -> bytes:
    """Return a small valid JPEG whose bytes differ by color."""
    buffer = BytesIO()
    Image.new('RGB', (20, 20), color=color).save(buffer, format='JPEG')
    return buffer.getvalue()


def test_image_library_authentication_protects_page_api_and_media(client):
    """Anonymous requests cannot discover image metadata or protected bytes."""
    assert client.get('/api/student-images').status_code == 401
    assert client.get('/student-images').status_code == 302
    assert client.get('/media/student-images/1').status_code == 302


def test_image_library_requires_active_class_after_login(client):
    """Authentication alone does not provide an image-library class scope."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
    })

    assert client.get('/api/student-images').get_json() == {
        'error': 'active_class_required'
    }
    assert client.get('/api/student-images').status_code == 409
    assert client.get('/student-images').headers['Location'].endswith('/classes')
    assert client.get('/media/student-images/1').headers['Location'].endswith('/classes')


def test_valid_active_class_list_is_paginated_and_ignores_class_override(
    app, client, two_classes, jpeg_bytes
):
    """List results always come from the session class and expose paging metadata."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        first = upload_image(first_class_id, 'first.jpg', jpeg_bytes)
        upload_image(second_class_id, 'second.jpg', jpeg_bytes)
        first_id = first.id

    login_and_select(client, first_class_id)
    response = client.get(
        f'/api/student-images?class_id={second_class_id}&page=0&per_page=999'
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['page'] == 1
    assert payload['per_page'] == 100
    assert payload['total'] == 1
    assert payload['pages'] == 1
    assert len(payload['items']) == 1
    assert payload['items'][0]['id'] == first_id
    assert payload['items'][0]['class_id'] == first_class_id


def test_image_list_rejects_unknown_status(client, two_classes):
    """A misspelled status is a validation error, not an empty successful list."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)

    response = client.get('/api/student-images?status=unknown')

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'invalid_status'


def test_unexpected_list_failure_returns_json_500_and_logs_class(
    client, two_classes, monkeypatch, caplog
):
    """Repository failures use the required safe 500 translation and audit log."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)

    def fail_list(*args, **kwargs):
        raise RuntimeError('simulated list failure')

    monkeypatch.setattr(StudentImageRepository, 'list_page', fail_list)
    with caplog.at_level(logging.ERROR):
        response = client.get('/api/student-images')

    assert response.status_code == 500
    assert response.get_json()['error']['code'] == 'request_failed'
    assert any(
        record.getMessage()
        == f'Student image request failed for class {first_class_id}'
        for record in caplog.records
    )


def test_unexpected_media_lookup_failure_returns_json_500(
    client, two_classes, monkeypatch, caplog
):
    """Media lookup failures use the same safe JSON response and class log."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)

    def fail_lookup(*args, **kwargs):
        raise RuntimeError('simulated media lookup failure')

    monkeypatch.setattr(StudentImageRepository, 'get_by_id', fail_lookup)
    with caplog.at_level(logging.ERROR):
        response = client.get('/media/student-images/1')

    assert response.status_code == 500
    assert response.get_json()['error']['code'] == 'request_failed'
    assert any(
        record.getMessage()
        == f'Student image request failed for class {first_class_id}'
        for record in caplog.records
    )


def test_cross_class_image_and_student_ids_return_not_found(
    app, client, two_classes, jpeg_bytes
):
    """Foreign image and student identifiers reveal no cross-class existence."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        foreign_student = add_student(second_class_id, 'FOREIGN001', 'Foreign')
        foreign_image = upload_image(second_class_id, 'foreign.jpg', jpeg_bytes)
        foreign_student_id = foreign_student.id
        foreign_image_id = foreign_image.id

    login_and_select(client, first_class_id)

    assert client.post(
        f'/api/student-images/{foreign_image_id}/bind',
        json={'student_id': foreign_student_id},
    ).status_code == 404
    assert client.delete(
        f'/api/student-images/{foreign_image_id}'
    ).status_code == 404
    assert client.post(
        f'/api/student/{foreign_student_id}/image',
        data={'file': (BytesIO(jpeg_bytes), 'portrait.jpg')},
        content_type='multipart/form-data',
    ).status_code == 404
    assert client.get(
        f'/media/student-images/{foreign_image_id}'
    ).status_code == 404


def test_batch_upload_accepts_files_field_and_returns_per_file_results(
    client, two_classes, jpeg_bytes
):
    """The multipart contract expands ZIPs and reports each processed image."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)
    archive = build_zip('inside.jpg', jpeg_bytes)

    response = client.post(
        '/api/student-images/batch',
        data={
            'files': [
                (BytesIO(jpeg_bytes), 'outside.jpg'),
                (BytesIO(archive), 'portraits.zip'),
            ]
        },
        content_type='multipart/form-data',
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['total_files'] == 2
    assert payload['pending_count'] == 1
    assert payload['duplicate_count'] == 1
    assert [item['filename'] for item in payload['results']] == [
        'outside.jpg',
        'inside.jpg',
    ]


def test_batch_upload_requires_nonempty_files_field(client, two_classes):
    """A missing plural files field is rejected as a client validation error."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)

    response = client.post('/api/student-images/batch', data={})

    assert response.status_code == 400
    assert response.get_json()['error']['code'] == 'files_required'


def test_bind_succeeds_for_pending_image(app, client, two_classes, jpeg_bytes):
    """A pending image can be bound to a student in the active class."""
    first_class_id, _ = two_classes
    with app.app_context():
        student = add_student(first_class_id, 'BIND001', 'Bind Student')
        image = upload_image(first_class_id, 'pending.jpg', jpeg_bytes)
        student_id, image_id = student.id, image.id
    login_and_select(client, first_class_id)

    response = client.post(
        f'/api/student-images/{image_id}/bind',
        json={'student_id': student_id},
    )

    assert response.status_code == 200
    assert response.get_json()['student_id'] == student_id
    assert response.get_json()['match_status'] == 'matched'


def test_bind_conflict_requires_confirmation_and_confirmed_bind_replaces_target(
    app, client, two_classes
):
    """Destructive binding returns 409 until the caller confirms replacement."""
    first_class_id, _ = two_classes
    with app.app_context():
        student = add_student(first_class_id, 'REPLACE001', 'Replace Student')
        source = upload_image(first_class_id, 'source.jpg', colored_jpeg((1, 2, 3)))
        target = upload_image(first_class_id, 'target.jpg', colored_jpeg((4, 5, 6)))
        target.student_id = student.id
        target.match_status = 'matched'
        db.session.commit()
        student_id, source_id, target_id = student.id, source.id, target.id
    login_and_select(client, first_class_id)

    conflict = client.post(
        f'/api/student-images/{source_id}/bind',
        json={'student_id': student_id},
    )
    confirmed = client.post(
        f'/api/student-images/{source_id}/bind',
        json={'student_id': student_id, 'confirm_replace': True},
    )

    assert conflict.status_code == 409
    assert conflict.get_json()['error']['code'] == 'binding_conflict'
    assert confirmed.status_code == 200
    assert confirmed.get_json()['id'] == source_id
    with app.app_context():
        assert db.session.get(StudentImage, target_id) is None


def test_student_specific_upload_binds_and_replaces_existing_image(
    app, client, two_classes
):
    """The single-student upload endpoint atomically replaces the old portrait."""
    first_class_id, _ = two_classes
    with app.app_context():
        student = add_student(first_class_id, 'UPLOAD001', 'Upload Student')
        old = StudentImageService.process_upload(
            first_class_id,
            FileStorage(
                stream=BytesIO(colored_jpeg((1, 1, 1))), filename='old.jpg'
            ),
            preferred_student_id=student.id,
        )
        student_id, old_id = student.id, old['image']['id']
    login_and_select(client, first_class_id)

    response = client.post(
        f'/api/student/{student_id}/image',
        data={'file': (BytesIO(colored_jpeg((2, 2, 2))), 'new.jpg')},
        content_type='multipart/form-data',
    )

    assert response.status_code == 200
    assert response.get_json()['image']['id'] == old_id
    assert response.get_json()['image']['student_id'] == student_id


def test_delete_removes_image(app, client, two_classes, jpeg_bytes):
    """Delete reports success and removes both image metadata and protected media."""
    first_class_id, _ = two_classes
    with app.app_context():
        image = upload_image(first_class_id, 'delete.jpg', jpeg_bytes)
        path = StudentImageService.get_storage_path(image)
        image_id = image.id
    login_and_select(client, first_class_id)

    response = client.delete(f'/api/student-images/{image_id}')

    assert response.status_code == 200
    assert response.get_json() == {'success': True}
    assert not path.exists()
    with app.app_context():
        assert db.session.get(StudentImage, image_id) is None


def test_media_returns_jpeg_with_private_cache_etag_and_conditional_response(
    app, client, two_classes, jpeg_bytes
):
    """Protected media is cacheable only privately and supports ETag validation."""
    first_class_id, _ = two_classes
    with app.app_context():
        image = upload_image(first_class_id, 'media.jpg', jpeg_bytes)
        image_id = image.id
    login_and_select(client, first_class_id)

    response = client.get(f'/media/student-images/{image_id}')
    conditional = client.get(
        f'/media/student-images/{image_id}',
        headers={'If-None-Match': response.headers['ETag']},
    )

    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'
    assert response.headers['Cache-Control'] == 'private, max-age=3600'
    assert response.headers['ETag']
    assert conditional.status_code == 304


def test_missing_media_returns_default_avatar_and_logs_record_id(
    app, client, two_classes, jpeg_bytes, caplog
):
    """A stale database row degrades safely and leaves an actionable error log."""
    first_class_id, _ = two_classes
    with app.app_context():
        image = upload_image(first_class_id, 'missing.jpg', jpeg_bytes)
        StudentImageService.get_storage_path(image).unlink()
        image_id = image.id
    login_and_select(client, first_class_id)

    with caplog.at_level(logging.ERROR):
        response = client.get(f'/media/student-images/{image_id}')

    assert response.status_code == 200
    assert response.mimetype == 'image/svg+xml'
    assert response.headers['Cache-Control'] == 'private, max-age=3600'
    assert b'<svg' in response.data
    assert any(str(image_id) in record.getMessage() for record in caplog.records)
