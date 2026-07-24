import pytest

from models import (
    ClassInfo,
    Student,
    StudentBehavior,
    StudentKnowledgeMastery,
    StudentPractice,
    WarningRecord,
    db,
)


def _login(client):
    response = client.post(
        '/login',
        data={'username': 'admin', 'password': 'correct-password'},
    )
    assert response.status_code == 302


def _seed_comparison_data(app, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        first = Student(student_no='20260001', name='甲', class_id=first_id)
        second = Student(student_no='20260002', name='乙', class_id=second_id)
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add_all([
            StudentBehavior(student_id=first.id, attendance_rate=90),
            StudentBehavior(student_id=second.id, attendance_rate=50),
            StudentPractice(student_id=first.id, avg_experiment_score=80),
            StudentPractice(student_id=second.id, avg_experiment_score=60),
            StudentKnowledgeMastery(
                student_id=first.id,
                knowledge_name='栈',
                mastery_rate=80,
            ),
            StudentKnowledgeMastery(
                student_id=first.id,
                knowledge_name='队列',
                mastery_rate=60,
            ),
            StudentKnowledgeMastery(
                student_id=second.id,
                knowledge_name='栈',
                mastery_rate=40,
            ),
            WarningRecord(
                student_id=second.id,
                warning_type='综合',
                warning_level=2,
                warning_score=70,
            ),
            WarningRecord(
                student_id=second.id,
                warning_type='实践',
                warning_level=3,
                warning_score=85,
            ),
        ])
        db.session.commit()


def test_compare_returns_separate_aggregate_metrics(app, client, two_classes):
    _seed_comparison_data(app, two_classes)
    first_id, second_id = two_classes
    _login(client)

    response = client.get(
        f'/api/classes/compare?class_id={first_id}&class_id={second_id}'
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert [row['class_id'] for row in rows] == [first_id, second_id]
    assert rows[0] == {
        'class_id': first_id,
        'class_name': '青年1班',
        'student_count': 1,
        'avg_attendance_rate': 90,
        'avg_practice_score': 80,
        'avg_mastery_rate': 70,
        'warning_count': 0,
        'warning_rate': 0,
    }
    assert rows[1] == {
        'class_id': second_id,
        'class_name': '青年2班',
        'student_count': 1,
        'avg_attendance_rate': 50,
        'avg_practice_score': 60,
        'avg_mastery_rate': 40,
        'warning_count': 1,
        'warning_rate': 100,
    }
    serialized = response.get_data(as_text=True)
    for student_detail_key in ('students', 'student_id', 'student_no'):
        assert student_detail_key not in serialized
    assert '甲' not in serialized
    assert '乙' not in serialized


@pytest.mark.parametrize('query_kind', ['one', 'duplicate'])
def test_compare_requires_two_distinct_classes(client, two_classes, query_kind):
    first_id, _ = two_classes
    _login(client)
    query = f'class_id={first_id}'
    if query_kind == 'duplicate':
        query += f'&class_id={first_id}'

    response = client.get(f'/api/classes/compare?{query}')

    assert response.status_code == 400
    assert response.get_json()['error'] == 'at_least_two_distinct_classes_required'


def test_compare_rejects_a_missing_class_id(client, two_classes):
    first_id, second_id = two_classes
    _login(client)

    response = client.get(
        f'/api/classes/compare?class_id={first_id}&class_id={second_id + 999}'
    )

    assert response.status_code == 400
    assert response.get_json() == {
        'error': 'class_not_found',
        'class_id': second_id + 999,
    }


def test_compare_empty_class_has_consistent_empty_metrics(app, client, two_classes):
    first_id, _ = two_classes
    with app.app_context():
        empty = ClassInfo(class_name='空班', status='archived')
        db.session.add(empty)
        db.session.commit()
        empty_id = empty.id
    _login(client)

    response = client.get(
        f'/api/classes/compare?class_id={first_id}&class_id={empty_id}'
    )

    assert response.status_code == 200
    empty_row = response.get_json()[1]
    assert empty_row == {
        'class_id': empty_id,
        'class_name': '空班',
        'student_count': 0,
        'avg_attendance_rate': 0,
        'avg_practice_score': 0,
        'avg_mastery_rate': None,
        'warning_count': 0,
        'warning_rate': 0,
    }


def test_compare_matches_single_class_metric_sources(app, client, two_classes):
    _seed_comparison_data(app, two_classes)
    first_id, second_id = two_classes
    _login(client)
    client.post(f'/api/classes/{second_id}/select')

    comparison = client.get(
        f'/api/classes/compare?class_id={first_id}&class_id={second_id}'
    ).get_json()[1]
    dashboard = client.get('/api/stats').get_json()
    knowledge = client.get('/api/knowledge/statistics').get_json()
    expected_mastery = round(
        sum(row['avg_mastery_rate'] for row in knowledge) / len(knowledge), 2
    )

    assert comparison['student_count'] == dashboard['total_students']
    assert comparison['avg_attendance_rate'] == dashboard['avg_attendance_rate']
    assert comparison['warning_count'] == dashboard['warning_count'] == 1
    assert comparison['avg_mastery_rate'] == expected_mastery


def test_compare_page_lists_active_and_archived_classes_without_changing_context(
    app, client, two_classes
):
    first_id, second_id = two_classes
    with app.app_context():
        archived = ClassInfo(class_name='<script>alert(1)</script>', status='archived')
        db.session.add(archived)
        db.session.commit()
        archived_id = archived.id
    _login(client)
    client.post(f'/api/classes/{second_id}/select')

    response = client.get('/class-compare')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'class-compare-select' in page
    assert 'class-compare-table' in page
    assert 'class-compare-chart' in page
    assert page.count('class="nav-link active"') == 1
    assert f'value="{first_id}"' in page
    assert f'value="{archived_id}"' in page
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    with client.session_transaction() as session:
        assert session['active_class_id'] == second_id
