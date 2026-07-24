from pathlib import Path

from models import Student, db


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def test_pages_show_active_class(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    for path in ['/', '/students', '/knowledge', '/warning', '/import']:
        response = client.get(path)

        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert '当前班级' in page
        assert '青年1班' in page
        assert '切换班级' in page


def test_page_without_active_class_redirects_to_classes(client):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})

    response = client.get('/students')

    assert response.status_code == 302
    assert '/classes' in response.headers['Location']


def test_base_template_centralizes_session_expiry_redirects():
    template = (PROJECT_ROOT / 'templates' / 'base.html').read_text(encoding='utf-8')

    assert '$(document).ajaxError' in template
    assert "window.location.href = '/login'" in template
    assert "xhr.responseJSON.error === 'active_class_required'" in template
    assert "window.location.href = '/classes'" in template


def test_data_pages_use_current_class_empty_state_contract():
    template_paths = [
        'templates/dashboard/index.html',
        'templates/student/list.html',
        'templates/knowledge/index.html',
        'templates/warning/index.html',
        'templates/import/index.html',
    ]

    for relative_path in template_paths:
        template = (PROJECT_ROOT / relative_path).read_text(encoding='utf-8')
        assert 'currentClassEmptyRow' in template

    base_template = (PROJECT_ROOT / 'templates' / 'base.html').read_text(encoding='utf-8')
    assert '当前班级暂无数据' in base_template
    assert "url_for('import.import_page')" in base_template


def test_chart_pages_clear_visualizations_when_the_active_class_has_no_data():
    for relative_path in [
        'templates/dashboard/index.html',
        'templates/knowledge/index.html',
        'templates/warning/index.html',
    ]:
        template = (PROJECT_ROOT / relative_path).read_text(encoding='utf-8')
        assert 'renderCurrentClassEmptyChart' in template


def test_empty_class_radar_contract_prevents_dashboard_chart_rendering(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    stats = client.get('/api/stats')
    radar = client.get('/api/radar')

    assert stats.status_code == 200
    assert stats.get_json()['total_students'] == 0
    assert radar.status_code == 200
    assert radar.get_json() == {
        'indicator': [],
        'student_count': 0,
        'values': [],
    }


def test_dashboard_radar_checks_the_api_student_count_before_initializing_echarts():
    template = (PROJECT_ROOT / 'templates/dashboard/index.html').read_text(encoding='utf-8')

    guard = "if (!data.student_count) {\n                renderCurrentClassEmptyChart('#radar-chart');\n                return;\n            }"
    assert guard in template
    assert template.index(guard) < template.index("echarts.init(document.getElementById('radar-chart'))")


def test_student_detail_radar_uses_empty_state_before_chart_initialization():
    template = (PROJECT_ROOT / 'templates/student/detail.html').read_text(encoding='utf-8')

    guard = "renderCurrentClassEmptyChart('#radar-chart');"
    assert guard in template
    assert template.index(guard) < template.index("echarts.init(document.getElementById('radar-chart'))")


def test_student_without_behavior_has_an_empty_radar_contract(app, client, two_classes):
    first_id, _ = two_classes
    with app.app_context():
        student = Student(student_no='20260001', name='无行为数据学生', class_id=first_id)
        db.session.add(student)
        db.session.commit()
        student_id = student.id

    login_and_select(client, first_id)
    response = client.get(f'/api/student/{student_id}/radar')

    assert response.status_code == 200
    assert response.get_json() == {'indicator': [], 'values': []}


def test_student_overview_empty_renderers_use_current_class_import_rows():
    template = (PROJECT_ROOT / 'templates/student/overview.html').read_text(encoding='utf-8')

    for selector, colspan in [
        ('#behavior-table', 2),
        ('#practice-table', 2),
        ('#knowledge-summary-table', 2),
        ('#knowledge-table', 9),
        ('#assignment-table', 11),
        ('#warning-table', 6),
    ]:
        assert "$(%r).html(currentClassEmptyRow(%d));" % (selector, colspan) in template


def test_each_data_loader_uses_a_class_aware_empty_row():
    expectations = {
        'templates/dashboard/index.html': [
            "$('#warning-table').html(currentClassEmptyRow(5));",
            "$('#weak-knowledge-table').html(currentClassEmptyRow(2));",
        ],
        'templates/student/list.html': ['html = currentClassEmptyRow(7);'],
        'templates/knowledge/index.html': [
            'html = currentClassEmptyRow(8);',
            'html = currentClassEmptyRow(7);',
            'html = currentClassEmptyRow(5);',
        ],
        'templates/warning/index.html': ['html = currentClassEmptyRow(7);'],
        'templates/import/index.html': ['html = currentClassEmptyRow(6);'],
    }

    for relative_path, assertions in expectations.items():
        template = (PROJECT_ROOT / relative_path).read_text(encoding='utf-8')
        for assertion in assertions:
            assert assertion in template


def test_warning_page_refers_to_current_class_students(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)

    page = client.get('/warning').get_data(as_text=True)

    assert '当前班级学生' in page
    assert '所有学生的风险情况' not in page
