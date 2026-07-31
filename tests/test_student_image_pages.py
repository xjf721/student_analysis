"""Page contracts for the student image library."""

from pathlib import Path

from models import Student, StudentImage, db


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def login_and_select(client, class_id: int) -> None:
    """Authenticate the test client and select one active class."""
    client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
    })
    client.post(f'/api/classes/{class_id}/select')


def add_image(class_id: int, student_id: int, suffix: str) -> StudentImage:
    """Persist one matched image without touching the filesystem."""
    image = StudentImage(
        class_id=class_id,
        student_id=student_id,
        original_filename=f'portrait-{suffix}.jpg',
        storage_filename=f'portrait-{suffix}.jpg',
        match_status='matched',
        mime_type='image/jpeg',
        file_size=123,
        content_hash=suffix.zfill(64),
    )
    db.session.add(image)
    db.session.commit()
    return image


def test_student_apis_return_persisted_avatar_url_or_null(
    app, client, two_classes
):
    """Both student APIs expose only the persisted protected portrait URL."""
    first_class_id, _ = two_classes
    with app.app_context():
        pictured = Student(
            student_no='PAGE001', name='Pictured Student', class_id=first_class_id
        )
        unpictured = Student(
            student_no='PAGE002', name='Unpictured Student', class_id=first_class_id
        )
        db.session.add_all([pictured, unpictured])
        db.session.flush()
        image = add_image(first_class_id, pictured.id, '101')
        pictured_id = pictured.id
        unpictured_id = unpictured.id
        image_id = image.id
    login_and_select(client, first_class_id)

    detail = client.get(f'/api/student/{pictured_id}').get_json()
    overview = client.get(f'/api/student/{pictured_id}/overview').get_json()
    empty_detail = client.get(f'/api/student/{unpictured_id}').get_json()
    empty_overview = client.get(
        f'/api/student/{unpictured_id}/overview'
    ).get_json()

    assert detail['avatar_url'] == f'/media/student-images/{image_id}'
    assert overview['basic']['avatar_url'] == f'/media/student-images/{image_id}'
    assert empty_detail['avatar_url'] is None
    assert empty_overview['basic']['avatar_url'] is None


def test_student_profile_page_uses_shared_portrait_controls(
    app, client, two_classes
):
    """The profile renders the shared 132 by 166 avatar chooser contract."""
    first_class_id, _ = two_classes
    with app.app_context():
        student = Student(
            student_no='PROFILE001', name='Profile Student', class_id=first_class_id
        )
        db.session.add(student)
        db.session.commit()
        student_id = student.id
    login_and_select(client, first_class_id)

    response = client.get(f'/student/{student_id}')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for marker in (
        'id="student-avatar"',
        'id="student-avatar-default"',
        'width: 132px',
        'height: 166px',
        'object-fit: cover',
        '从图像库选择',
        '本地上传',
        'avatar-library-modal',
        'avatar-library-grid',
        'avatar-local-upload',
        '/static/js/student_avatar.js',
        'StudentAvatar.mount({',
    ):
        assert marker in page
    template = (PROJECT_ROOT / 'templates' / 'student' / 'detail.html').read_text(
        encoding='utf-8'
    )
    assert "{% include 'student/_avatar_modal.html' %}" in template


def test_student_overview_page_uses_responsive_three_column_avatar_header(
    app, client, two_classes
):
    """The overview header separates portrait, information, and actions."""
    first_class_id, _ = two_classes
    with app.app_context():
        student = Student(
            student_no='OVERVIEW001', name='Overview Student', class_id=first_class_id
        )
        db.session.add(student)
        db.session.commit()
        student_id = student.id
    login_and_select(client, first_class_id)

    response = client.get(f'/student/{student_id}/overview')

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for marker in (
        'student-overview-header',
        'student-overview-portrait',
        'student-overview-info',
        'student-overview-actions',
        'grid-template-columns: 160px minmax(0, 1fr) auto',
        '@media (max-width: 767.98px)',
        'id="student-avatar"',
        'id="student-avatar-default"',
        'width: 132px',
        'height: 166px',
        'object-fit: cover',
        '从图像库选择',
        '本地上传',
        'avatar-library-modal',
        'avatar-library-grid',
        'avatar-local-upload',
        '/static/js/student_avatar.js',
        'StudentAvatar.mount({',
    ):
        assert marker in page
    template = (
        PROJECT_ROOT / 'templates' / 'student' / 'overview.html'
    ).read_text(encoding='utf-8')
    assert "{% include 'student/_avatar_modal.html' %}" in template


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
