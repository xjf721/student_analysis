import pytest

from models import (
    ClassInfo,
    ImportRecord,
    Student,
    StudentBehavior,
    StudentKnowledgeMastery,
    WarningRecord,
    db,
)
from repositories import (
    BehaviorRepository,
    KnowledgeRepository,
    StudentRepository,
    WarningRepository,
)
from services.analysis import (
    BehaviorAnalyzer,
    KnowledgeAnalyzer,
    PracticeAnalyzer,
    WarningEngine,
)


def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def seed_two_class_students(app, first_id, second_id):
    with app.app_context():
        first = Student(student_no='20260001', name='一班学生', class_id=first_id)
        second = Student(student_no='20260002', name='二班学生', class_id=second_id)
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add_all([
            StudentBehavior(student_id=first.id, attendance_rate=90, behavior_score=80),
            StudentBehavior(student_id=second.id, attendance_rate=20, behavior_score=10),
            StudentKnowledgeMastery(
                student_id=first.id, knowledge_name='当前班知识点', mastery_rate=30
            ),
            StudentKnowledgeMastery(
                student_id=second.id, knowledge_name='其他班知识点', mastery_rate=95
            ),
            WarningRecord(
                student_id=first.id,
                warning_type='attendance',
                warning_level=2,
                warning_score=70,
                warning_reason='current',
            ),
            WarningRecord(
                student_id=second.id,
                warning_type='practice',
                warning_level=3,
                warning_score=99,
                warning_reason='other',
            ),
        ])
        db.session.commit()
        return first.id, second.id


@pytest.mark.parametrize(
    'path',
    ['/', '/students', '/student/1', '/student/1/overview', '/knowledge', '/warning'],
)
def test_business_pages_require_active_class(client, path):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})

    response = client.get(path)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/classes')


@pytest.mark.parametrize(
    'method,path',
    [
        ('get', '/api/stats'),
        ('get', '/api/radar'),
        ('get', '/api/warning-ranking'),
        ('get', '/api/heatmap'),
        ('get', '/api/knowledge-ranking'),
        ('get', '/api/students'),
        ('get', '/api/student/1'),
        ('get', '/api/student/1/radar'),
        ('get', '/api/student/1/weak-points'),
        ('get', '/api/student/1/theory-practice'),
        ('get', '/api/student/1/class-comparison'),
        ('get', '/api/student/1/overview'),
        ('get', '/api/knowledge/list'),
        ('get', '/api/knowledge/statistics'),
        ('get', '/api/knowledge/point-summary'),
        ('get', '/api/knowledge/students?knowledge_name=x'),
        ('get', '/api/knowledge/x/students'),
        ('get', '/api/knowledge/heatmap'),
        ('get', '/api/knowledge/weak-points'),
        ('get', '/api/warning/students'),
        ('get', '/api/warning/statistics'),
        ('get', '/api/warning/distribution'),
        ('get', '/api/warning/by-level/2'),
        ('post', '/api/warning/refresh'),
    ],
)
def test_business_apis_require_active_class(client, method, path):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})

    response = getattr(client, method)(path)

    assert response.status_code == 409
    assert response.get_json() == {'error': 'active_class_required'}


def test_stale_active_class_is_cleared_for_api_and_page(client):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    with client.session_transaction() as session:
        session['active_class_id'] = 999999

    assert client.get('/api/stats').status_code == 409
    with client.session_transaction() as session:
        assert 'active_class_id' not in session

    with client.session_transaction() as session:
        session['active_class_id'] = 999999
    assert client.get('/students').status_code == 302
    with client.session_transaction() as session:
        assert 'active_class_id' not in session


def test_archived_active_class_is_cleared(client, two_classes, app):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    with app.app_context():
        ClassInfo.query.filter_by(id=first_id).update({'status': 'archived'})
        db.session.commit()

    response = client.get('/api/students')

    assert response.status_code == 409
    with client.session_transaction() as session:
        assert 'active_class_id' not in session


def test_lists_search_details_and_dashboard_are_scoped(app, client, two_classes):
    first_id, second_id = two_classes
    first_student_id, second_student_id = seed_two_class_students(app, first_id, second_id)
    login_and_select(client, first_id)

    rows = client.get('/api/students').get_json()
    assert [row['name'] for row in rows] == ['一班学生']
    assert client.get('/api/students?keyword=二班').get_json() == []
    assert [row['name'] for row in client.get('/api/students?keyword=一班').get_json()] == ['一班学生']

    for suffix in ['', '/radar', '/weak-points', '/theory-practice', '/class-comparison', '/overview']:
        assert client.get(f'/api/student/{second_student_id}{suffix}').status_code == 404
    assert client.get(f'/student/{second_student_id}').status_code == 404
    assert client.get(f'/student/{second_student_id}/overview').status_code == 404
    assert client.get(f'/api/student/{first_student_id}').status_code == 200

    stats = client.get('/api/stats').get_json()
    assert stats['total_students'] == 1
    assert stats['avg_attendance_rate'] == 90
    assert stats['warning_count'] == 1
    assert stats['weak_knowledge_count'] == 1


def test_query_class_id_cannot_override_session(app, client, two_classes):
    first_id, second_id = two_classes
    seed_two_class_students(app, first_id, second_id)
    login_and_select(client, first_id)

    students = client.get(f'/api/students?class_id={second_id}').get_json()
    warning_stats = client.get(f'/api/warning/statistics?class_id={second_id}').get_json()
    heatmap = client.get(f'/api/knowledge/heatmap?class_id={second_id}').get_json()

    assert [item['class_id'] for item in students] == [first_id]
    assert warning_stats['total_warnings'] == 1
    assert heatmap['students'] == ['一班学生']
    assert heatmap['knowledge'] == ['当前班知识点']


def test_debug_stats_endpoint_is_removed(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    assert client.get('/api/debug/stats').status_code == 404


@pytest.mark.parametrize(
    'call',
    [
        StudentRepository.get_all,
        StudentRepository.get_count,
        BehaviorRepository.get_all,
        BehaviorRepository.get_statistics,
        KnowledgeRepository.get_all_knowledge_names,
        KnowledgeRepository.get_knowledge_statistics,
        WarningRepository.get_statistics,
        WarningRepository.get_type_distribution,
    ],
)
def test_repository_class_scoped_queries_reject_empty_calls(call):
    with pytest.raises(TypeError):
        call()


@pytest.mark.parametrize(
    'analyzer', [BehaviorAnalyzer, KnowledgeAnalyzer, PracticeAnalyzer, WarningEngine]
)
@pytest.mark.parametrize('class_id', [None, 0])
def test_analyzers_require_class_id(analyzer, class_id):
    with pytest.raises(ValueError, match='class_id is required'):
        analyzer(class_id)


@pytest.mark.parametrize(
    'method,path',
    [
        ('get', '/import'),
        ('post', '/api/import/upload'),
        ('post', '/api/import/folder'),
        ('get', '/api/import/records'),
        ('post', '/api/import/analyze'),
        ('get', '/api/import/types'),
    ],
)
def test_import_routes_require_active_class(client, method, path):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})

    response = getattr(client, method)(path)

    if path == '/import':
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/classes')
    else:
        assert response.status_code == 409
        assert response.get_json() == {'error': 'active_class_required'}


def test_stale_active_class_is_cleared_for_import_records(client):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    with client.session_transaction() as session:
        session['active_class_id'] = 999999

    response = client.get('/api/import/records')

    assert response.status_code == 409
    with client.session_transaction() as session:
        assert 'active_class_id' not in session


def test_import_records_are_scoped_and_query_override_is_ignored(app, client, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        db.session.add_all([
            ImportRecord(
                class_id=first_id,
                filename='first.xlsx',
                file_hash='a' * 64,
                uploaded_by='admin',
                import_type='rain_classroom',
            ),
            ImportRecord(
                class_id=second_id,
                filename='second.xlsx',
                file_hash='b' * 64,
                uploaded_by='admin',
                import_type='rain_classroom',
            ),
        ])
        db.session.commit()
    login_and_select(client, first_id)

    response = client.get(f'/api/import/records?class_id={second_id}')

    assert response.status_code == 200
    assert [item['filename'] for item in response.get_json()] == ['first.xlsx']
    assert [item['class_id'] for item in response.get_json()] == [first_id]


def test_warning_refresh_preserves_other_class_records(app, two_classes):
    first_id, second_id = two_classes
    _, second_student_id = seed_two_class_students(app, first_id, second_id)
    with app.app_context():
        other_warning = WarningRecord.query.filter_by(student_id=second_student_id).one()
        other_warning_id = other_warning.id
        other_warning_score = other_warning.warning_score

        WarningEngine(first_id).refresh_warnings()

        preserved = db.session.get(WarningRecord, other_warning_id)
        assert preserved is not None
        assert preserved.student_id == second_student_id
        assert preserved.warning_score == other_warning_score
        assert WarningRecord.query.join(Student).filter(Student.class_id == second_id).count() == 1


def test_automatic_warning_analysis_removes_warning_after_student_becomes_safe(
    app, two_classes
):
    first_id, second_id = two_classes
    first_student_id, second_student_id = seed_two_class_students(
        app, first_id, second_id
    )
    with app.app_context():
        behavior = StudentBehavior.query.filter_by(student_id=first_student_id).one()
        behavior.attendance_rate = 10
        behavior.video_finish_rate = 10
        db.session.commit()

        engine = WarningEngine(first_id)
        engine.analyze_all()
        assert WarningRecord.query.filter_by(student_id=first_student_id).count() == 1

        behavior.attendance_rate = 100
        behavior.video_finish_rate = 100
        behavior.behavior_score = 100
        db.session.commit()
        engine.analyze_all()

        assert WarningRecord.query.filter_by(student_id=first_student_id).count() == 0
        assert WarningRecord.query.filter_by(student_id=second_student_id).count() == 1


def test_automatic_warning_analysis_removes_warning_when_behavior_is_removed(
    app, two_classes
):
    first_id, second_id = two_classes
    first_student_id, second_student_id = seed_two_class_students(
        app, first_id, second_id
    )
    with app.app_context():
        engine = WarningEngine(first_id)
        engine.analyze_all()
        assert WarningRecord.query.filter_by(student_id=first_student_id).count() == 1

        behavior = StudentBehavior.query.filter_by(student_id=first_student_id).one()
        db.session.delete(behavior)
        db.session.commit()
        engine.analyze_all()

        assert WarningRecord.query.filter_by(student_id=first_student_id).count() == 0
        assert WarningRecord.query.filter_by(student_id=second_student_id).count() == 1
