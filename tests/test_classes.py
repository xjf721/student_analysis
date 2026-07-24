from models import ImportRecord, KnowledgePointSummary, Student, db


def login(client):
    return client.post('/login', data={'username': 'admin', 'password': 'correct-password'})


def test_create_select_archive_restore_and_delete_empty(app, client):
    login(client)
    created = client.post('/api/classes', json={
        'class_name': '青年3班', 'term': '2026春', 'teacher_name': '张老师', 'notes': '测试班'
    })
    assert created.status_code == 201
    class_id = created.get_json()['id']

    selected = client.post(f'/api/classes/{class_id}/select')
    assert selected.status_code == 200
    with client.session_transaction() as session:
        assert session['active_class_id'] == class_id

    assert client.post(f'/api/classes/{class_id}/archive').status_code == 200
    with client.session_transaction() as session:
        assert 'active_class_id' not in session

    assert client.post(f'/api/classes/{class_id}/restore').status_code == 200
    assert client.delete(f'/api/classes/{class_id}').status_code == 200


def test_class_with_students_cannot_be_deleted(app, client, two_classes):
    login(client)
    first_id, _ = two_classes
    with app.app_context():
        db.session.add(Student(student_no='20260001', name='甲', class_id=first_id))
        db.session.commit()

    response = client.delete(f'/api/classes/{first_id}')
    assert response.status_code == 409


def test_class_pages_use_bootstrap_five_modal_markup(client):
    login(client)

    response = client.get('/classes')

    assert response.status_code == 200
    assert b'data-bs-toggle="modal"' in response.data
    assert b'data-bs-target="#create-class-modal"' in response.data


def test_class_api_rejects_non_object_payload(client):
    login(client)

    malformed = client.post('/api/classes', json=[])
    assert malformed.status_code == 400
    assert malformed.get_json()['error'] == 'invalid_class_payload'


def test_class_page_includes_edit_form_and_patch_request(client, two_classes):
    login(client)

    response = client.get('/classes')

    assert response.status_code == 200
    assert b'id="edit-class-form"' in response.data
    assert b'data-bs-target="#edit-class-modal"' in response.data
    assert b"type:'PATCH'" in response.data


def test_edit_class_updates_allowed_fields_and_rejects_invalid_payload(client, two_classes):
    login(client)
    first_id, _ = two_classes

    updated = client.patch(f'/api/classes/{first_id}', json={
        'class_name': '青年1班（更新）',
        'teacher_name': '李老师',
        'term': '2026秋',
        'notes': '已编辑',
    })

    assert updated.status_code == 200
    assert updated.get_json()['class_name'] == '青年1班（更新）'
    assert updated.get_json()['teacher_name'] == '李老师'
    assert updated.get_json()['term'] == '2026秋'
    assert updated.get_json()['notes'] == '已编辑'

    invalid = client.patch(f'/api/classes/{first_id}', json={'teacher_name': 1})
    assert invalid.status_code == 400
    assert invalid.get_json()['error'] == 'invalid_class_payload'


def test_selecting_archived_class_is_rejected_without_setting_active_class(client, two_classes):
    login(client)
    first_id, _ = two_classes
    assert client.post(f'/api/classes/{first_id}/archive').status_code == 200

    selected = client.post(f'/api/classes/{first_id}/select')

    assert selected.status_code == 404
    with client.session_transaction() as session:
        assert 'active_class_id' not in session


def test_unauthenticated_class_api_request_is_rejected(client):
    response = client.get('/api/classes')

    assert response.status_code == 401
    assert response.get_json()['error'] == 'authentication_required'


def test_class_with_import_record_cannot_be_deleted(app, client, two_classes):
    login(client)
    first_id, _ = two_classes
    with app.app_context():
        db.session.add(ImportRecord(
            class_id=first_id,
            filename='rain.xlsx',
            file_hash='a' * 64,
            uploaded_by='admin',
            import_type='rain_classroom',
        ))
        db.session.commit()

    assert client.delete(f'/api/classes/{first_id}').status_code == 409


def test_class_with_knowledge_summary_cannot_be_deleted(app, client, two_classes):
    login(client)
    first_id, _ = two_classes
    with app.app_context():
        db.session.add(KnowledgePointSummary(
            class_id=first_id,
            knowledge_name='链表',
            mastery_rate=80.0,
        ))
        db.session.commit()

    assert client.delete(f'/api/classes/{first_id}').status_code == 409
