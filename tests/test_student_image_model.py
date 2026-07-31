from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from models import ClassInfo, Student, StudentImage, db
from repositories import StudentImageRepository


def create_image(class_id: int, **overrides) -> StudentImage:
    """Build a valid image row with test-local defaults."""
    values = {
        'class_id': class_id,
        'original_filename': 'portrait.jpg',
        'storage_filename': 'portrait-1.jpg',
        'match_status': 'pending',
        'mime_type': 'image/jpeg',
        'file_size': 1024,
        'content_hash': 'a' * 64,
    }
    values.update(overrides)
    return StudentImage(**values)


def test_app_creates_student_image_folder(app):
    folder = Path(app.config['STUDENT_IMAGE_FOLDER'])

    assert folder.exists()
    assert folder.is_dir()


def test_student_image_table_has_required_columns(app):
    with app.app_context():
        columns = {item['name'] for item in inspect(db.engine).get_columns('student_image')}

    assert {
        'id', 'class_id', 'student_id', 'original_filename', 'storage_filename',
        'parsed_student_no', 'number_match_type', 'parsed_name', 'match_status',
        'match_message', 'mime_type', 'file_size', 'content_hash',
        'created_at', 'updated_at',
    } <= columns


def test_pending_images_allow_multiple_null_student_ids(app, two_classes):
    class_id, _ = two_classes
    with app.app_context():
        db.session.add_all([
            create_image(class_id),
            create_image(
                class_id,
                original_filename='portrait-2.jpg',
                storage_filename='portrait-2.jpg',
                content_hash='b' * 64,
            ),
        ])
        db.session.commit()

        assert StudentImage.query.filter_by(class_id=class_id, student_id=None).count() == 2


def test_student_can_have_only_one_image(app, two_classes):
    class_id, _ = two_classes
    with app.app_context():
        student = Student(student_no='IMAGE001', name='Student One', class_id=class_id)
        db.session.add(student)
        db.session.flush()
        db.session.add(create_image(class_id, student_id=student.id))
        db.session.commit()

        db.session.add(create_image(
            class_id,
            student_id=student.id,
            original_filename='replacement.jpg',
            storage_filename='replacement.jpg',
            content_hash='c' * 64,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_cross_class_student_image_binding_is_rejected(app, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        student = Student(student_no='IMAGE003', name='Student Three', class_id=second_id)
        db.session.add(student)
        db.session.flush()
        db.session.add(create_image(first_id, student_id=student.id))

        with pytest.raises(ValueError, match='class_id'):
            db.session.commit()
        db.session.rollback()


def test_repository_scopes_suffix_search_to_requested_class(app, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        first_student = Student(student_no='FIRST01', name='First Student', class_id=first_id)
        second_student = Student(student_no='SECOND01', name='Second Student', class_id=second_id)
        db.session.add_all([first_student, second_student])
        db.session.flush()
        first_image = create_image(
            first_id,
            student_id=first_student.id,
            parsed_student_no='01',
            number_match_type='suffix',
            match_status='matched',
        )
        second_image = create_image(
            second_id,
            student_id=second_student.id,
            original_filename='second-01.jpg',
            storage_filename='second-01.jpg',
            parsed_student_no='01',
            number_match_type='suffix',
            content_hash='d' * 64,
        )
        db.session.add_all([first_image, second_image])
        db.session.commit()

        assert StudentImageRepository.get_by_id(second_image.id, first_id) is None
        assert StudentImageRepository.get_for_student(second_student.id, first_id) is None
        page = StudentImageRepository.list_page(first_id, None, '01', 1, 24)
        assert [image.id for image in page.items] == [first_image.id]


def test_image_serialization_includes_media_url(app, two_classes):
    class_id, _ = two_classes
    with app.app_context():
        student = Student(student_no='IMAGE002', name='Student Two', class_id=class_id)
        db.session.add(student)
        db.session.flush()
        image = create_image(class_id, student_id=student.id)
        db.session.add(image)
        db.session.commit()

        data = image.to_dict()
        assert data['avatar_url'] == f'/media/student-images/{image.id}'
        assert data['student_no'] == 'IMAGE002'
        assert data['student_name'] == 'Student Two'
