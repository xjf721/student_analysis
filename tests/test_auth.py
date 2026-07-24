from werkzeug.security import generate_password_hash


def test_business_page_requires_login(client):
    response = client.get('/')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_api_requires_login(client):
    response = client.get('/api/stats')

    assert response.status_code == 401
    assert response.get_json()['error'] == 'authentication_required'


def test_login_and_logout(client):
    bad = client.post('/login', data={'username': 'admin', 'password': 'wrong'})
    assert bad.status_code == 401

    good = client.post('/login', data={
        'username': 'admin',
        'password': 'correct-password',
    })
    assert good.status_code == 302
    assert '/classes' in good.headers['Location']

    with client.session_transaction() as session:
        assert session['authenticated'] is True
        assert session['admin_username'] == 'admin'

    logout = client.post('/logout')
    assert logout.status_code == 302
    with client.session_transaction() as session:
        assert 'authenticated' not in session
        assert 'active_class_id' not in session


def test_missing_credentials_fail_closed(app, client):
    app.config['ADMIN_USERNAME'] = None
    app.config['ADMIN_PASSWORD_HASH'] = None

    response = client.post('/login', data={'username': 'admin', 'password': 'x'})

    assert response.status_code == 503
    assert '管理员凭据尚未配置' in response.get_data(as_text=True)


def test_csrf_rejects_missing_token(tmp_path):
    from app import create_app

    csrf_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'csrf.db'}",
        'ADMIN_USERNAME': 'admin',
        'ADMIN_PASSWORD_HASH': generate_password_hash('correct-password'),
        'WTF_CSRF_ENABLED': True,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'csrf-test-secret',
    })

    response = csrf_app.test_client().post('/login', data={
        'username': 'admin', 'password': 'correct-password',
    })

    assert response.status_code == 400


def test_login_rate_limit(tmp_path):
    from app import create_app

    limited_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'limit.db'}",
        'ADMIN_USERNAME': 'admin',
        'ADMIN_PASSWORD_HASH': generate_password_hash('correct-password'),
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': True,
        'SECRET_KEY': 'limit-test-secret',
    })
    limited_client = limited_app.test_client()

    for _ in range(5):
        response = limited_client.post('/login', data={
            'username': 'admin', 'password': 'wrong',
        })
        assert response.status_code == 401

    response = limited_client.post('/login', data={
        'username': 'admin', 'password': 'wrong',
    })
    assert response.status_code == 429
