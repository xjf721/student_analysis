from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from controllers import import_controller
from models import ImportRecord, Student, StudentImage, db
from services.importers.base_importer import BaseImporter
from services.student_image_service import StudentImageService


class LegacyImporter(BaseImporter):
    @property
    def import_type(self) -> str:
        return 'legacy'

    def get_expected_columns(self):
        return []

    def parse(self):
        return True, []

    def _save_to_db(self) -> int:
        return 1


def login_and_select(client, class_id: int) -> None:
    """Authenticate and select the class used by import APIs."""
    client.post('/login', data={
        'username': 'admin', 'password': 'correct-password',
    })
    client.post(f'/api/classes/{class_id}/select')


@pytest.mark.parametrize('import_mode', ['upload', 'folder'])
def test_successful_import_rematches_images_only_in_target_class(
    app, client, two_classes, jpeg_bytes, tmp_path, monkeypatch, import_mode
):
    """Each successful import request rematches only its selected class."""
    first_id, second_id = two_classes
    image_filename = '01-李少飞.jpg'
    with app.app_context():
        first_result = StudentImageService.process_upload(
            first_id,
            FileStorage(stream=BytesIO(jpeg_bytes), filename=image_filename),
        )
        second_result = StudentImageService.process_upload(
            second_id,
            FileStorage(stream=BytesIO(jpeg_bytes), filename=image_filename),
        )
        first_image_id = first_result['image']['id']
        second_image_id = second_result['image']['id']

    def successful_import(
        file_path: str, class_id: int, uploaded_by: str, **kwargs
    ) -> dict:
        student = Student.query.filter_by(
            class_id=class_id, student_no='20260001'
        ).first()
        if student is None:
            db.session.add(
                Student(student_no='20260001', name='李少飞', class_id=class_id)
            )
            db.session.commit()
        return {'success': True, 'message': 'imported', 'imported_count': 1}

    monkeypatch.setattr(import_controller, 'import_data', successful_import)
    monkeypatch.setattr(
        import_controller,
        'run_all_analysis',
        lambda class_id: {'summary': {'success': True}},
    )
    login_and_select(client, first_id)

    if import_mode == 'upload':
        response = client.post(
            '/api/import/upload',
            data={
                'class_id': str(first_id),
                'file': [
                    (BytesIO(b'first excel'), 'alpha.xlsx'),
                    (BytesIO(b'second excel'), 'beta.xlsx'),
                ],
            },
            content_type='multipart/form-data',
        )
    else:
        (tmp_path / 'alpha.xlsx').write_bytes(b'first excel')
        (tmp_path / 'beta.xlsx').write_bytes(b'second excel')
        response = client.post('/api/import/folder', json={
            'class_id': first_id,
            'folder': str(tmp_path),
        })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['image_matching']['checked_count'] == 1
    assert payload['image_matching']['matched_count'] == 1
    with app.app_context():
        imported_student = Student.query.filter_by(
            class_id=first_id, student_no='20260001'
        ).one()
        assert db.session.get(StudentImage, first_image_id).student_id == imported_student.id
        untouched = db.session.get(StudentImage, second_image_id)
        assert untouched.student_id is None
        assert untouched.match_status == 'pending'


def test_legacy_filename_duplicate_lookup_remains_supported(app, two_classes):
    first_id, _ = two_classes
    with app.app_context():
        record = ImportRecord(
            class_id=first_id,
            filename='legacy.xlsx',
            file_hash='a' * 64,
            uploaded_by='admin',
            import_type='legacy',
            import_status='成功',
        )
        db.session.add(record)
        db.session.commit()

        assert ImportRecord.is_imported('legacy.xlsx')


def test_explicit_importer_creates_class_scoped_record_and_preserves_other_class(app, two_classes, tmp_path):
    first_id, second_id = two_classes
    file_path = Path(tmp_path) / '2026春-青年1班-雨课堂-legacy.xlsx'
    file_path.write_bytes(b'legacy import content')

    with app.app_context():
        importer = LegacyImporter(str(file_path), first_id, 'admin')
        importer.parsed_data = [{'value': 1}]

        saved, _ = importer.save()
        assert saved
        first_record = importer.import_record
        assert first_record.class_id == first_id
        assert len(first_record.file_hash) == 64
        assert first_record.uploaded_by == 'admin'
        assert ImportRecord.is_imported(importer.filename)
        assert ImportRecord.is_imported(first_record.class_id, first_record.file_hash)
        first_class_id = first_record.class_id
        file_hash = first_record.file_hash

        other_class_record = ImportRecord(
            class_id=second_id,
            filename=importer.filename,
            file_hash=file_hash,
            uploaded_by='admin',
            import_type='legacy',
            import_status='成功',
        )
        db.session.add(other_class_record)
        db.session.commit()

        saved, _ = importer.save()
        assert saved
        assert db.session.get(ImportRecord, other_class_record.id) is not None
        assert ImportRecord.query.filter_by(
            class_id=first_class_id,
            file_hash=file_hash,
        ).count() == 1


def test_import_records_endpoint_requires_and_uses_class_selection(app, client, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        db.session.add_all([
            ImportRecord(
                class_id=first_id,
                filename='first.xlsx',
                file_hash='a' * 64,
                uploaded_by='admin',
                import_type='legacy',
                import_status='成功',
            ),
            ImportRecord(
                class_id=second_id,
                filename='second.xlsx',
                file_hash='b' * 64,
                uploaded_by='admin',
                import_type='legacy',
                import_status='成功',
            ),
        ])
        db.session.commit()

    anonymous_response = client.get('/api/import/records?limit=20')
    assert anonymous_response.status_code == 401

    login = client.post('/login', data={
        'username': 'admin', 'password': 'correct-password',
    })
    assert login.status_code == 302

    response = client.get('/api/import/records?limit=20')
    assert response.status_code == 409

    selected = client.post(f'/api/classes/{first_id}/select')
    assert selected.status_code == 200
    response = client.get(f'/api/import/records?limit=20&class_id={second_id}')

    assert response.status_code == 200
    assert [record['class_id'] for record in response.get_json()] == [first_id]


def test_default_csrf_rejects_existing_post_routes_without_a_token(tmp_path):
    test_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'csrf-default.db'}",
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'csrf-default-secret',
    })
    with test_app.app_context():
        db.drop_all()
        db.create_all()

    response = test_app.test_client().post('/api/import/analyze')

    assert response.status_code == 400

    with test_app.app_context():
        db.session.remove()
        db.drop_all()
