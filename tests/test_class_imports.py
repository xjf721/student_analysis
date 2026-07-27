from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from models import (
    ClassInfo,
    ImportRecord,
    Student,
    StudentKnowledgeMastery,
    db,
)
from services.importers.base_importer import BaseImporter, calculate_file_hash
from services.importers.rainclass_importer import RainClassSummaryImporter


def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def test_filename_class_mismatch_requires_confirmation(
    client, two_classes, tmp_path, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append((args, kwargs)),
    )

    with file_path.open('rb') as stream:
        response = client.post('/api/import/upload', data={
            'class_id': str(first_id),
            'file': (stream, file_path.name),
        })

    assert response.status_code == 409
    payload = response.get_json()
    assert payload['error'] == 'class_name_mismatch'
    assert payload['selected_class'] == '青年1班'
    assert payload['detected_class'] == '青年2班'
    assert imported == []


def test_confirmed_upload_preserves_filename_and_uses_explicit_target(
    client, two_classes, tmp_path, monkeypatch
):
    first_id, second_id = two_classes
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')
    observed = {}

    def fake_import(file_path, class_id, uploaded_by, **kwargs):
        observed.update(
            file_path=file_path,
            class_id=class_id,
            uploaded_by=uploaded_by,
            **kwargs,
        )
        return {'success': True, 'imported_count': 1, 'class_id': class_id}

    analyzed = []
    monkeypatch.setattr('controllers.import_controller.import_data', fake_import)
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: analyzed.append(class_id) or {'summary': {'success': True}},
    )
    assert client.post(f'/api/classes/{second_id}/select').status_code == 200

    with file_path.open('rb') as stream:
        response = client.post('/api/import/upload', data={
            'class_id': str(second_id),
            'confirm_class_mismatch': 'true',
            'file': (stream, file_path.name),
        })

    assert response.status_code == 200
    assert observed['class_id'] == second_id
    assert observed['uploaded_by'] == 'admin'
    assert observed['original_filename'] == file_path.name
    assert len(observed['file_hash']) == 64
    assert analyzed == [second_id]


def test_upload_rejects_tampered_class_id_before_import(
    client, two_classes, tmp_path, monkeypatch
):
    first_id, second_id = two_classes
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append((args, kwargs)),
    )

    with file_path.open('rb') as stream:
        response = client.post('/api/import/upload', data={
            'class_id': str(second_id),
            'file': (stream, file_path.name),
        })

    assert response.status_code == 409
    assert response.get_json()['error'] == 'class_context_mismatch'
    assert imported == []


def test_upload_rejects_archived_target_class(
    app, client, two_classes, tmp_path, monkeypatch
):
    first_id, second_id = two_classes
    with app.app_context():
        ClassInfo.query.filter_by(id=second_id).update({'status': 'archived'})
        db.session.commit()
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append((args, kwargs)),
    )

    with file_path.open('rb') as stream:
        response = client.post('/api/import/upload', data={
            'class_id': str(second_id),
            'file': (stream, file_path.name),
        })

    assert response.status_code == 409
    assert response.get_json()['error'] == 'class_context_mismatch'
    assert imported == []


def test_analysis_receives_target_class(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    observed = []
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: observed.append(class_id) or {'summary': {'success': True}},
    )

    response = client.post('/api/import/analyze')

    assert response.status_code == 200
    assert observed == [first_id]


def test_switching_target_class_aligns_history_and_analysis(
    app, client, two_classes, monkeypatch
):
    first_id, second_id = two_classes
    with app.app_context():
        db.session.add_all([
            ImportRecord(
                class_id=first_id,
                filename='first.xlsx',
                file_hash='1' * 64,
                uploaded_by='admin',
                import_type='test',
                import_status='成功',
            ),
            ImportRecord(
                class_id=second_id,
                filename='second.xlsx',
                file_hash='2' * 64,
                uploaded_by='admin',
                import_type='test',
                import_status='成功',
            ),
        ])
        db.session.commit()
    login_and_select(client, first_id)
    observed = []
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: observed.append(class_id) or {'summary': {'success': True}},
    )

    assert client.post(f'/api/classes/{second_id}/select').status_code == 200
    records = client.get('/api/import/records').get_json()
    response = client.post('/api/import/analyze')

    assert [record['filename'] for record in records] == ['second.xlsx']
    assert response.status_code == 200
    assert observed == [second_id]


def test_folder_import_surfaces_class_mismatch(
    client, two_classes, tmp_path, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append((args, kwargs)),
    )

    response = client.post('/api/import/folder', json={
        'class_id': first_id,
        'folder': str(tmp_path),
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['failed_files'] == 1
    assert payload['results'][0]['error'] == 'class_name_mismatch'
    assert payload['results'][0]['selected_class'] == '青年1班'
    assert payload['results'][0]['detected_class'] == '青年2班'
    assert imported == []


def test_folder_import_rejects_tampered_class_context(
    client, two_classes, tmp_path, monkeypatch
):
    first_id, second_id = two_classes
    login_and_select(client, first_id)
    (tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx').write_bytes(b'fake excel')
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append((args, kwargs)),
    )

    response = client.post('/api/import/folder', json={
        'class_id': second_id,
        'folder': str(tmp_path),
    })

    assert response.status_code == 409
    assert response.get_json()['error'] == 'class_context_mismatch'
    assert imported == []


def test_same_filename_is_independent_between_classes(app, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        db.session.add_all([
            ImportRecord(
                class_id=first_id,
                filename='成绩单.xlsx',
                file_hash='a' * 64,
                uploaded_by='admin',
                import_type='雨课堂',
                import_status='成功',
            ),
            ImportRecord(
                class_id=second_id,
                filename='成绩单.xlsx',
                file_hash='a' * 64,
                uploaded_by='admin',
                import_type='雨课堂',
                import_status='成功',
            ),
        ])
        db.session.commit()

        assert ImportRecord.query.filter_by(filename='成绩单.xlsx').count() == 2


class ExplodingImporter(BaseImporter):
    @property
    def import_type(self):
        return 'test'

    def get_expected_columns(self):
        return []

    def parse(self):
        return True, []

    def _save_to_db(self):
        db.session.add(Student(
            student_no='atomic-student',
            name='不应保留',
            class_id=self._get_target_class_id(),
        ))
        db.session.flush()
        raise RuntimeError('boom')


class ParseFailImporter(BaseImporter):
    @property
    def import_type(self):
        return 'test'

    def get_expected_columns(self):
        return []

    def _read_file(self):
        return pd.DataFrame([{'value': 1}])

    def parse(self):
        return False, ['无法解析测试文件']

    def _save_to_db(self):
        raise AssertionError('parse failure must not save')


class PhaseExceptionImporter(BaseImporter):
    def __init__(self, *args, fail_phase, **kwargs):
        super().__init__(*args, **kwargs)
        self.fail_phase = fail_phase

    @property
    def import_type(self):
        return 'test'

    def get_expected_columns(self):
        return []

    def validate(self):
        if self.fail_phase == 'validate':
            raise RuntimeError('boom-validate')
        self.df = pd.DataFrame([{'value': 1}])
        return True, []

    def clean(self):
        if self.fail_phase == 'clean':
            raise RuntimeError('boom-clean')
        return True, []

    def parse(self):
        if self.fail_phase == 'parse':
            raise RuntimeError('boom-parse')
        self.parsed_data = [{'value': 1}]
        return True, []

    def _save_to_db(self):
        if self.fail_phase == 'save':
            raise RuntimeError('boom-save')
        return 1


def test_failed_save_rolls_back_data_and_records_failure(app, two_classes, tmp_path):
    first_id, _ = two_classes
    file_path = tmp_path / 'atomic.xlsx'
    file_path.write_bytes(b'atomic')

    with app.app_context():
        importer = ExplodingImporter(
            str(file_path), first_id, 'admin', display_filename='原始名称.xlsx'
        )
        importer.parsed_data = [{'value': 1}]

        success, message = importer.save()

        assert success is False
        assert 'boom' in message
        assert Student.query.filter_by(student_no='atomic-student').count() == 0
        record = ImportRecord.query.filter_by(class_id=first_id).one()
        assert record.filename == '原始名称.xlsx'
        assert record.import_status == '失败'
        assert 'boom' in record.error_message


def test_validation_failure_records_failed_import(app, two_classes, tmp_path):
    first_id, _ = two_classes
    file_path = tmp_path / 'invalid.txt'
    file_path.write_bytes(b'invalid')

    with app.app_context():
        importer = ParseFailImporter(str(file_path), first_id, 'admin')

        result = importer.execute()

        assert result['success'] is False
        record = ImportRecord.query.filter_by(class_id=first_id).one()
        assert record.import_status == '失败'
        assert '不支持的文件格式' in record.error_message


def test_parse_failure_records_failed_import(app, two_classes, tmp_path):
    first_id, _ = two_classes
    file_path = tmp_path / 'parse.xlsx'
    file_path.write_bytes(b'not parsed')

    with app.app_context():
        importer = ParseFailImporter(str(file_path), first_id, 'admin')

        result = importer.execute()

        assert result['success'] is False
        record = ImportRecord.query.filter_by(class_id=first_id).one()
        assert record.import_status == '失败'
        assert '无法解析测试文件' in record.error_message


@pytest.mark.parametrize('phase', ['validate', 'clean', 'parse', 'save'])
def test_stage_exception_rolls_back_and_records_readable_failure(
    app, two_classes, tmp_path, phase
):
    first_id, _ = two_classes
    file_path = tmp_path / f'{phase}.xlsx'
    file_path.write_bytes(phase.encode())

    with app.app_context():
        importer = PhaseExceptionImporter(
            str(file_path), first_id, 'admin', fail_phase=phase
        )

        result = importer.execute()

        assert result['success'] is False
        assert phase in ' '.join(result['errors'])
        records = ImportRecord.query.filter_by(class_id=first_id).all()
        assert len(records) == 1
        assert records[0].import_status == '失败'
        assert phase in records[0].error_message


def test_failed_audit_persistence_is_not_silently_swallowed(
    app, two_classes, tmp_path, monkeypatch
):
    first_id, _ = two_classes
    file_path = tmp_path / 'audit.xlsx'
    file_path.write_bytes(b'audit')

    with app.app_context():
        importer = ParseFailImporter(str(file_path), first_id, 'admin')
        monkeypatch.setattr(
            db.session,
            'commit',
            lambda: (_ for _ in ()).throw(RuntimeError('audit database unavailable')),
        )

        with pytest.raises(RuntimeError, match='失败审计记录保存失败'):
            importer._record_failed_import('original failure')


def test_unknown_excel_type_records_failed_import(app, two_classes, tmp_path, monkeypatch):
    from controllers.import_controller import import_data

    first_id, _ = two_classes
    file_path = tmp_path / 'unknown.xlsx'
    file_path.write_bytes(b'unknown')
    monkeypatch.setattr(
        'services.importers.parser_utils.read_excel_smart',
        lambda *args, **kwargs: pd.DataFrame([{'陌生列': 1}]),
    )

    with app.app_context():
        result = import_data(
            str(file_path), first_id, 'admin', file_hash=calculate_file_hash(file_path)
        )

        assert result['success'] is False
        record = ImportRecord.query.filter_by(class_id=first_id).one()
        assert record.import_status == '失败'
        assert record.filename == file_path.name
        assert '无法识别文件类型' in record.error_message


def test_cross_class_student_number_collision_does_not_move_student(
    app, two_classes, tmp_path
):
    first_id, second_id = two_classes
    file_path = tmp_path / 'summary.xlsx'
    file_path.write_bytes(b'collision')

    with app.app_context():
        student = Student(student_no='20260001', name='一班学生', class_id=first_id)
        db.session.add(student)
        db.session.commit()
        student_id = student.id

        importer = RainClassSummaryImporter(
            str(file_path),
            second_id,
            'admin',
            display_filename='2026春-青年2班-雨课堂-学生汇总.xlsx',
        )
        importer.parsed_data = [{
            'student_no': '20260001',
            'name': '二班同号学生',
            'overall_mastery_rate': 80,
            'completion_rate': 90,
            'self_test_correct_rate': 70,
        }]

        success, message = importer.save()

        assert success is False
        assert '已属于其他班级' in message
        preserved = db.session.get(Student, student_id)
        assert preserved.class_id == first_id
        assert preserved.name == '一班学生'
        assert StudentKnowledgeMastery.query.count() == 0
        failed = ImportRecord.query.filter_by(class_id=second_id).one()
        assert failed.import_status == '失败'


def test_calculate_file_hash_is_sha256(tmp_path):
    file_path = tmp_path / 'payload.xlsx'
    file_path.write_bytes(b'abc')

    assert calculate_file_hash(Path(file_path)) == (
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    )


def test_clear_all_web_endpoint_is_removed(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    assert client.post('/api/import/clear-all').status_code == 404


def test_general_import_page_has_target_class_picker_and_no_clear_button(
    client, two_classes
):
    first_id, second_id = two_classes
    login_and_select(client, first_id)

    response = client.get('/import')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="class_id"' in html
    assert f'value="{first_id}" selected' in html
    assert f'value="{second_id}"' in html
    assert 'confirm_class_mismatch' in html
    assert "'/api/classes/' + this.value + '/select'" in html
    assert 'escapeHtml(data.import_type)' in html
    assert 'escapeHtml(errorMsg)' in html
    assert 'escapeHtml(item.filename)' in html
    assert 'escapeHtml(data.results[key].message)' in html
    assert ".text(fileName || '选择文件...')" in html
    assert 'clear-data-btn' not in html
    assert '/api/import/clear-all' not in html


def test_class_detail_has_locked_upload_for_its_class(client, two_classes):
    first_id, second_id = two_classes
    login_and_select(client, first_id)

    response = client.get(f'/classes/{second_id}')
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-bs-toggle="collapse"' in html
    assert 'data-bs-target="#class-upload-panel"' in html
    assert 'id="class-upload-form"' in html
    assert f'name="class_id" value="{second_id}"' in html
    assert 'confirm_class_mismatch' in html
    assert '/api/import/upload' in html
    with client.session_transaction() as session:
        assert session['active_class_id'] == second_id


def test_class_detail_exposes_reanalysis_for_the_current_class(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    html = client.get(f'/classes/{first_id}').get_data(as_text=True)

    assert 'id="class-reanalyze-btn"' in html
    assert "url: '/api/import/analyze'" in html
    assert '重新分析本班' in html


def test_import_query_class_synchronizes_active_session(client, two_classes):
    first_id, second_id = two_classes
    login_and_select(client, first_id)

    response = client.get(f'/import?class_id={second_id}')

    assert response.status_code == 200
    assert f'value="{second_id}" selected' in response.get_data(as_text=True)
    with client.session_transaction() as session:
        assert session['active_class_id'] == second_id


def test_multi_file_upload_imports_in_order_and_analyzes_once(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported, analyzed = [], []
    def fake_import(file_path, class_id, uploaded_by, **kwargs):
        imported.append(kwargs['original_filename'])
        return {'success': True, 'import_type': 'test', 'imported_count': 2}
    monkeypatch.setattr('controllers.import_controller.import_data', fake_import)
    monkeypatch.setattr('controllers.import_controller.run_all_analysis', lambda class_id: analyzed.append(class_id) or {'summary': {'success': True}})
    response = client.post('/api/import/upload', data={'class_id': str(first_id), 'file': [(BytesIO(b'first'), 'rain_first.xlsx'), (BytesIO(b'second'), 'rain_second.xlsx')]})
    payload = response.get_json()
    assert response.status_code == 200
    assert imported == ['rain_first.xlsx', 'rain_second.xlsx']
    assert analyzed == [first_id]
    assert payload['success'] is True
    assert payload['total_files'] == 2
    assert payload['imported_files'] == 2
    assert payload['failed_files'] == 0
    assert payload['total_imported_rows'] == 4


def test_multi_file_upload_continues_after_file_failure(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    def fake_import(file_path, class_id, uploaded_by, **kwargs):
        filename = kwargs['original_filename']; imported.append(filename)
        return {'success': filename != 'bad.xlsx', 'imported_count': 0 if filename == 'bad.xlsx' else 3}
    monkeypatch.setattr('controllers.import_controller.import_data', fake_import)
    monkeypatch.setattr('controllers.import_controller.run_all_analysis', lambda class_id: {'summary': {'success': True}})
    payload = client.post('/api/import/upload', data={'class_id': str(first_id), 'file': [(BytesIO(b'bad'), 'bad.xlsx'), (BytesIO(b'good'), 'good.xlsx')]}).get_json()
    assert imported == ['bad.xlsx', 'good.xlsx']
    assert payload['success'] is False and payload['partial_success'] is True
    assert payload['imported_files'] == 1 and payload['failed_files'] == 1
    assert payload['total_imported_rows'] == 3


def test_multi_file_class_mismatch_is_preflighted_before_any_import(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append(kwargs['original_filename']),
    )

    conflicting_filename = '\u9752\u5e742\u73ed-\u96e8\u8bfe\u5802.xlsx'
    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': [
            (BytesIO(b'ok'), '\u9752\u5e741\u73ed-\u96e8\u8bfe\u5802.xlsx'),
            (BytesIO(b'conflict'), conflicting_filename),
        ],
    })

    payload = response.get_json()
    assert response.status_code == 409
    assert payload['error'] == 'class_name_mismatch'
    assert payload['conflicting_files'] == [conflicting_filename]
    assert imported == []


def test_multi_file_upload_rejects_unsupported_format_before_any_import(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    monkeypatch.setattr('controllers.import_controller.import_data', lambda *args, **kwargs: imported.append(kwargs['original_filename']))
    response = client.post('/api/import/upload', data={'class_id': str(first_id), 'file': [(BytesIO(b'ok'), 'ok.xlsx'), (BytesIO(b'bad'), 'bad.csv')]})
    assert response.status_code == 400
    assert response.get_json()['unsupported_files'] == ['bad.csv']
    assert imported == []


def test_single_file_upload_keeps_legacy_response_shape(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    monkeypatch.setattr('controllers.import_controller.import_data', lambda *args, **kwargs: {'success': True, 'import_type': 'test', 'imported_count': 7})
    monkeypatch.setattr('controllers.import_controller.run_all_analysis', lambda class_id: {'summary': {'success': True}})
    payload = client.post('/api/import/upload', data={'class_id': str(first_id), 'file': (BytesIO(b'one'), 'one.xlsx')}).get_json()
    assert payload['imported_count'] == 7
    assert 'results' not in payload and 'total_files' not in payload
    assert 'filename' not in payload


def test_single_file_upload_import_exception_keeps_legacy_500(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('import failed')),
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': (BytesIO(b'one'), 'one.xlsx'),
    })

    assert response.status_code == 500
    assert response.get_json() == {'success': False, 'message': 'import failed'}
