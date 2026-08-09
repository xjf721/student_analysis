"""Tests for deterministic, class-scoped student image matching."""

from dataclasses import FrozenInstanceError

import pytest

from models import Student, db
from services.student_image_service import (
    ImageMatchResult,
    ParsedStudentImage,
    StudentImageService,
)


def add_student(class_id: int, student_no: str, name: str) -> Student:
    """Persist and return a student fixture for the requested class."""
    student = Student(student_no=student_no, name=name, class_id=class_id)
    db.session.add(student)
    db.session.commit()
    return student


def test_parse_suffix_and_name():
    """Suffix-number filenames produce the suffix and normalized name."""
    parsed = StudentImageService.parse_filename('01-李少锋.jpg')

    assert parsed == ParsedStudentImage('01', 'suffix', '李少锋')


def test_parse_full_student_number_and_name():
    """Long student-number filenames produce the full number and name."""
    parsed = StudentImageService.parse_filename('202306142001江承阳.jpg')

    assert parsed == ParsedStudentImage('202306142001', 'full', '江承阳')


def test_parse_normalizes_whitespace_and_underscores_around_name():
    """Decorative whitespace, underscores, and hyphens do not become name data."""
    parsed = StudentImageService.parse_filename('01-__  李少锋  __.jpg')

    assert parsed == ParsedStudentImage('01', 'suffix', '李少锋')


def test_parse_unsupported_pattern_returns_empty_identity():
    """Unanchored or malformed identities are not guessed from a filename."""
    parsed = StudentImageService.parse_filename('portrait-01-李少锋.jpg')

    assert parsed == ParsedStudentImage(None, None, None)


def test_parse_valid_image_filename_without_identity_returns_empty_identity():
    """A normal image filename without a number/name convention remains pending."""
    parsed = StudentImageService.parse_filename('class-photo.jpg')

    assert parsed == ParsedStudentImage(None, None, None)


@pytest.mark.parametrize(
    ('result', 'field', 'replacement'),
    [
        (ParsedStudentImage('01', 'suffix', '李少锋'), 'name', '王同学'),
        (ImageMatchResult('pending', None, '待匹配'), 'status', 'matched'),
    ],
)
def test_result_objects_are_immutable(result, field, replacement):
    """Matching evidence and outcomes cannot be mutated after construction."""
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, replacement)


def test_match_returns_current_class_student_for_identical_suffix_and_name(app, two_classes):
    """Class scope prevents an identical candidate in another class from winning."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        first_student = add_student(first_class_id, '202306140001', '李少锋')
        add_student(second_class_id, '202406140001', '李少锋')

        result = StudentImageService.match_student(
            first_class_id,
            ParsedStudentImage('01', 'suffix', '李少锋'),
        )

        assert result.status == 'matched'
        assert result.student.id == first_student.id


def test_match_returns_matched_for_one_exact_suffix_candidate(app, two_classes):
    """One suffix and normalized-name candidate is associated automatically."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, '202306140001', '李少锋')

        result = StudentImageService.match_student(
            class_id,
            ParsedStudentImage('01', 'suffix', '李少锋'),
        )

        assert result == ImageMatchResult('matched', student, '已自动关联')


def test_match_returns_conflict_when_suffix_number_has_different_name(app, two_classes):
    """A matching suffix paired with another name must not bind automatically."""
    class_id, _ = two_classes
    with app.app_context():
        add_student(class_id, '202306140001', '李少锋')

        result = StudentImageService.match_student(
            class_id,
            ParsedStudentImage('01', 'suffix', '王同学'),
        )

        assert result.status == 'conflict'
        assert result.student is None


def test_match_returns_conflict_when_full_number_has_different_name(app, two_classes):
    """A matching full number paired with another name must not bind automatically."""
    class_id, _ = two_classes
    with app.app_context():
        add_student(class_id, '202306142001', '江承阳')

        result = StudentImageService.match_student(
            class_id,
            ParsedStudentImage('202306142001', 'full', '王同学'),
        )

        assert result.status == 'conflict'
        assert result.student is None


def test_match_returns_pending_when_current_class_has_no_candidate(app, two_classes):
    """Students in another class do not make the current class match or conflict."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        add_student(second_class_id, '202306140001', '李少锋')

        result = StudentImageService.match_student(
            first_class_id,
            ParsedStudentImage('01', 'suffix', '李少锋'),
        )

        assert result.status == 'pending'
        assert result.student is None


def test_match_returns_conflict_for_multiple_current_class_candidates(app, two_classes):
    """Multiple exact candidates are surfaced for manual resolution."""
    class_id, _ = two_classes
    with app.app_context():
        add_student(class_id, '202306140001', '李少锋')
        add_student(class_id, '202406140001', '李少锋')

        result = StudentImageService.match_student(
            class_id,
            ParsedStudentImage('01', 'suffix', '李少锋'),
        )

        assert result.status == 'conflict'
        assert result.student is None


def test_match_returns_pending_for_missing_identity(app, two_classes):
    """Missing identity fields never trigger a database match."""
    class_id, _ = two_classes
    with app.app_context():
        add_student(class_id, '202306140001', '李少锋')

        result = StudentImageService.match_student(
            class_id,
            StudentImageService.parse_filename('class-photo.jpg'),
        )

        assert result.status == 'pending'
        assert result.student is None
