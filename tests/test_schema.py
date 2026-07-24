from sqlalchemy import inspect

from models import ClassInfo, ImportRecord, db


def test_class_and_import_schema(app):
    with app.app_context():
        inspector = inspect(app.extensions['sqlalchemy'].engine)
        class_columns = {item['name'] for item in inspector.get_columns('class_info')}
        import_columns = {item['name'] for item in inspector.get_columns('import_record')}
        student_columns = {item['name']: item for item in inspector.get_columns('student')}

    assert {'status', 'notes'} <= class_columns
    assert {'class_id', 'file_hash', 'uploaded_by'} <= import_columns
    assert student_columns['class_id']['nullable'] is False


def test_class_and_import_record_serialization_are_class_aware(app, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        first = db.session.get(ClassInfo, first_id)
        first.notes = '重点关注班级'
        matching_record = ImportRecord(
            class_id=first_id,
            filename='first.xlsx',
            file_hash='a' * 64,
            uploaded_by='admin',
            import_type='雨课堂',
            import_status='成功',
        )
        other_record = ImportRecord(
            class_id=second_id,
            filename='second.xlsx',
            file_hash='b' * 64,
            uploaded_by='admin',
            import_type='头歌',
            import_status='成功',
        )
        db.session.add_all([matching_record, other_record])
        db.session.commit()

        assert ImportRecord.is_imported(first_id, matching_record.file_hash)
        assert not ImportRecord.is_imported(second_id, matching_record.file_hash)
        assert ImportRecord.get_recent_records(first_id) == [matching_record]
        assert first.to_dict()['status'] == 'active'
        assert first.to_dict()['notes'] == '重点关注班级'
        assert matching_record.to_dict()['class_id'] == first_id
        assert matching_record.to_dict()['class_name'] == '青年1班'
        assert matching_record.to_dict()['file_hash'] == 'a' * 64
        assert matching_record.to_dict()['uploaded_by'] == 'admin'
