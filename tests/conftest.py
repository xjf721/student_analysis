import os
from io import BytesIO

os.environ.setdefault('FLASK_ENV', 'test')

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app
from models import ClassInfo, db


@pytest.fixture()
def jpeg_bytes() -> bytes:
    """Return a valid landscape JPEG without relying on shared fixture files."""
    buffer = BytesIO()
    Image.new('RGB', (1200, 800), color=(80, 120, 160)).save(buffer, format='JPEG')
    return buffer.getvalue()


@pytest.fixture()
def app(tmp_path):
    test_app = create_app('test', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'test.db'}",
        'STUDENT_IMAGE_FOLDER': str(tmp_path / 'student_images'),
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
