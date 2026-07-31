"""Page contracts for the student image library."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def login_and_select(client, class_id: int) -> None:
    """Authenticate the test client and select one active class."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
    })
    client.post(f'/api/classes/{class_id}/select')


def test_image_library_page_exposes_upload_filter_grid_and_result_contract(
    client, two_classes
):
    """The active-class library renders every selector used by its UI code."""
    first_class_id, _ = two_classes
    login_and_select(client, first_class_id)

    response = client.get('/student-images')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for marker in (
        'id="image-grid"',
        'id="image-upload-input"',
        'id="zip-upload-input"',
        'id="status-filter"',
        'id="image-search"',
        'id="batch-result-modal"',
        '/api/student-images/batch',
    ):
        assert marker in page


def test_image_library_sidebar_link_follows_student_profile_navigation():
    """The sidebar links the library after profiles and scopes its active state."""
    template = (PROJECT_ROOT / 'templates' / 'base.html').read_text(
        encoding='utf-8'
    )

    profile_position = template.index('<p>学生画像</p>')
    library_position = template.index("url_for('student_image.index')")
    knowledge_position = template.index('<p>知识点分析</p>')

    assert profile_position < library_position < knowledge_position
    assert "request.endpoint.startswith('student_image.')" in template


def test_image_library_maps_page_state_to_the_list_api_contract():
    """The UI uses ``per_page`` and omits an empty status from list requests."""
    template = (
        PROJECT_ROOT / 'templates' / 'student_image' / 'index.html'
    ).read_text(encoding='utf-8')

    assert 'per_page: imageLibraryState.perPage' in template
    assert 'query.status = imageLibraryState.status' in template


def test_image_library_refetches_after_the_last_page_shrinks():
    """Deleting the final card on a page reloads the new last valid page."""
    template = (
        PROJECT_ROOT / 'templates' / 'student_image' / 'index.html'
    ).read_text(encoding='utf-8')

    assert 'imageLibraryState.page > Number(data.pages)' in template
    assert 'imageLibraryState.page = Number(data.pages);' in template


def test_image_library_waits_for_bind_modal_before_showing_replace_confirm():
    """The 409 confirmation modal opens after Bootstrap finishes hiding bind."""
    template = (
        PROJECT_ROOT / 'templates' / 'student_image' / 'index.html'
    ).read_text(encoding='utf-8')

    assert ".one('hidden.bs.modal'" in template
    assert 'payload.confirm_replace = true;' in template
