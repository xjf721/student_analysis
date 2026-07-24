from pathlib import Path

from app import create_app
from models import ImportRecord, db
from services.importers.base_importer import BaseImporter


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


def test_legacy_importer_creates_class_scoped_record_and_preserves_other_class(app, two_classes, tmp_path):
    _, second_id = two_classes
    file_path = Path(tmp_path) / '2026春-青年1班-雨课堂-legacy.xlsx'
    file_path.write_bytes(b'legacy import content')

    with app.app_context():
        importer = LegacyImporter(str(file_path))
        importer.parsed_data = [{'value': 1}]

        saved, _ = importer.save()
        assert saved
        first_record = importer.import_record
        assert first_record.class_id is not None
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


def test_import_records_endpoint_remains_global_until_class_selection_exists(app, client, two_classes):
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

    response = client.get('/api/import/records?limit=20')

    assert response.status_code == 200
    assert {record['class_id'] for record in response.get_json()} == {first_id, second_id}


def test_task_one_default_does_not_globally_block_existing_post_routes(tmp_path):
    test_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'csrf-default.db'}",
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'csrf-default-secret',
    })
    with test_app.app_context():
        db.drop_all()
        db.create_all()

    response = test_app.test_client().post('/api/import/clear-all')

    assert response.status_code == 200

    with test_app.app_context():
        db.session.remove()
        db.drop_all()
