from pathlib import Path


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
