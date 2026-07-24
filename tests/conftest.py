import os

os.environ.setdefault('FLASK_ENV', 'test')

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from models import ClassInfo, db


@pytest.fixture()
def app(tmp_path):
    test_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'test.db'}",
        'ADMIN_USERNAME': 'admin',
        'ADMIN_PASSWORD_HASH': generate_password_hash('correct-password'),
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-secret',
    })
    with test_app.app_context():
        db.drop_all()
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def two_classes(app):
    with app.app_context():
        first = ClassInfo(class_name='青年1班', term='2026春', status='active')
        second = ClassInfo(class_name='青年2班', term='2026春', status='active')
        db.session.add_all([first, second])
        db.session.commit()
        return first.id, second.id
