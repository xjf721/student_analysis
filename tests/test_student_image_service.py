"""Tests for safe student-image processing and lifecycle operations."""

import hashlib
from io import BytesIO
from pathlib import Path
import warnings
import zipfile

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from models import Student, StudentImage, db
from repositories import StudentImageRepository
from services.student_image_service import ImageProcessingError, StudentImageService


def uploaded_file(filename: str, content: bytes) -> FileStorage:
    """Build an in-memory upload with a stable display filename."""
    return FileStorage(stream=BytesIO(content), filename=filename)


def jpeg_with_color(color: tuple[int, int, int]) -> bytes:
    """Return a small valid JPEG whose bytes vary predictably by color."""
    buffer = BytesIO()
    Image.new('RGB', (20, 10), color=color).save(buffer, format='JPEG')
    return buffer.getvalue()


def encoded_image(format_name: str, size: tuple[int, int], mode: str = 'RGB') -> bytes:
    """Return a solid image encoded in the requested real source format."""
    buffer = BytesIO()
    Image.new(mode, size, color=0).save(buffer, format=format_name)
    return buffer.getvalue()


def zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    """Build one in-memory ZIP container from literal entry names and bytes."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def add_student(class_id: int, student_no: str, name: str) -> Student:
    """Persist one student used by image lifecycle tests."""
    student = Student(class_id=class_id, student_no=student_no, name=name)
    db.session.add(student)
    db.session.commit()
    return student


def pending_image(class_id: int, filename: str, content: bytes) -> StudentImage:
    """Upload and return one unmatched image backed by a real normalized file."""
    result = StudentImageService.process_upload(
        class_id, uploaded_file(filename, content)
    )
    return db.session.get(StudentImage, result['image']['id'])


def test_validation_rejects_invalid_bytes_disguised_as_jpeg(app, two_classes):
    """Content verification catches non-images even when the suffix is allowed."""
    class_id, _ = two_classes
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_upload(
            class_id, uploaded_file('01-Invalid.jpg', b'not an image')
        )

    assert error.value.code == 'invalid_image'


def test_validation_rejects_unsupported_extension(app, two_classes, jpeg_bytes):
    """Valid image bytes do not bypass the configured filename allow-list."""
    class_id, _ = two_classes
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_upload(
            class_id, uploaded_file('01-Invalid.gif', jpeg_bytes)
        )

    assert error.value.code == 'unsupported_extension'


def test_validation_rejects_gif_content_renamed_as_jpeg(app, two_classes):
    """An allowed suffix cannot disguise a Pillow-supported source format."""
    class_id, _ = two_classes
    disguised_gif = encoded_image('GIF', (20, 10))
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_upload(
            class_id, uploaded_file('disguised.jpg', disguised_gif)
        )

    assert error.value.code == 'unsupported_image_format'
    with app.app_context():
        assert StudentImage.query.filter_by(class_id=class_id).count() == 0


def test_validation_rejects_source_larger_than_five_megabytes(app, two_classes):
    """The per-image byte limit is enforced before image decoding."""
    class_id, _ = two_classes
    oversized = b'x' * (5 * 1024 * 1024 + 1)
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_upload(
            class_id, uploaded_file('01-Oversized.jpg', oversized)
        )

    assert error.value.code == 'file_too_large'


def test_validation_rejects_decoded_pixel_count_above_service_limit(app, two_classes):
    """A compact source cannot allocate an unbounded RGB image before thumbnailing."""
    class_id, _ = two_classes
    compact_large_png = encoded_image('PNG', (4600, 4600), mode='1')
    assert len(compact_large_png) < 5 * 1024 * 1024

    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_upload(
            class_id, uploaded_file('too-many-pixels.png', compact_large_png)
        )

    assert error.value.code == 'image_too_many_pixels'


def test_validation_converts_decompression_bomb_warning_to_image_error(app, two_classes):
    """Pillow bomb warnings are rejected rather than leaking or continuing decode."""
    class_id, _ = two_classes
    bomb_png = encoded_image('PNG', (10_000, 10_000), mode='1')
    assert len(bomb_png) < 5 * 1024 * 1024

    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with app.app_context(), pytest.raises(ImageProcessingError) as error:
            StudentImageService.process_upload(
                class_id, uploaded_file('bomb.png', bomb_png)
            )

    assert error.value.code == 'invalid_image'


def test_normalize_writes_real_bounded_jpeg(app, two_classes, jpeg_bytes):
    """Successful processing emits an RGB JPEG with a longest edge at most 1024."""
    class_id, _ = two_classes
    with app.app_context():
        result = StudentImageService.process_upload(
            class_id, uploaded_file('class-photo.png', jpeg_bytes)
        )
        image = db.session.get(StudentImage, result['image']['id'])
        storage_path = StudentImageService.get_storage_path(image)

        assert storage_path.parent == Path(app.config['STUDENT_IMAGE_FOLDER']) / str(class_id)
        assert storage_path.suffix == '.jpg'
        assert storage_path.exists()
        with Image.open(storage_path) as normalized:
            assert normalized.format == 'JPEG'
            assert normalized.mode == 'RGB'
            assert max(normalized.size) <= 1024


def test_batch_returns_one_result_for_each_valid_file(app, two_classes):
    """The aggregate accounts for every independently processed regular image."""
    class_id, _ = two_classes
    with app.app_context():
        result = StudentImageService.process_batch(class_id, [
            uploaded_file('first.jpg', jpeg_with_color((1, 2, 3))),
            uploaded_file('second.png', jpeg_with_color((4, 5, 6))),
        ])

        assert result == {
            'success': True,
            'total_files': 2,
            'matched_count': 0,
            'pending_count': 2,
            'conflict_count': 0,
            'duplicate_count': 0,
            'failed_count': 0,
            'results': result['results'],
        }
        assert [item['filename'] for item in result['results']] == ['first.jpg', 'second.png']


def test_batch_keeps_valid_sibling_when_one_file_fails(app, two_classes, jpeg_bytes):
    """A per-file validation failure does not roll back a successful sibling."""
    class_id, _ = two_classes
    with app.app_context():
        result = StudentImageService.process_batch(class_id, [
            uploaded_file('valid.jpg', jpeg_bytes),
            uploaded_file('invalid.jpg', b'not an image'),
        ])

        assert result['success'] is False
        assert result['pending_count'] == 1
        assert result['failed_count'] == 1
        assert StudentImage.query.filter_by(class_id=class_id).count() == 1


def test_batch_rejects_more_than_two_hundred_entries_before_processing(
    app, two_classes, jpeg_bytes
):
    """The entry-count guard runs before any item can create metadata or files."""
    class_id, _ = two_classes
    files = [uploaded_file(f'{index}.jpg', jpeg_bytes) for index in range(201)]
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_batch(class_id, files)

    assert error.value.code == 'too_many_files'
    with app.app_context():
        assert StudentImage.query.filter_by(class_id=class_id).count() == 0


def test_batch_rejects_zip_path_traversal_before_processing(app, two_classes, jpeg_bytes):
    """A parent path in any ZIP member prevents the archive from being processed."""
    class_id, _ = two_classes
    archive = uploaded_file('photos.zip', zip_bytes([('../escape.jpg', jpeg_bytes)]))
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_batch(class_id, [archive])

    assert error.value.code == 'unsafe_zip_entry'
    with app.app_context():
        assert StudentImage.query.filter_by(class_id=class_id).count() == 0


def test_batch_rejects_nested_zip(app, two_classes, jpeg_bytes):
    """Archive members cannot themselves be ZIP transfer containers."""
    class_id, _ = two_classes
    inner = zip_bytes([('photo.jpg', jpeg_bytes)])
    outer = uploaded_file('photos.zip', zip_bytes([('nested.zip', inner)]))
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_batch(class_id, [outer])

    assert error.value.code == 'nested_zip'


def test_batch_bounds_expanded_zip_content_by_request_limit(app, two_classes):
    """The expanded-size guard rejects a ZIP before decoding any member."""
    class_id, _ = two_classes
    app.config['MAX_CONTENT_LENGTH'] = 100
    archive = uploaded_file('photos.zip', zip_bytes([('large.jpg', b'x' * 101)]))
    with app.app_context(), pytest.raises(ImageProcessingError) as error:
        StudentImageService.process_batch(class_id, [archive])

    assert error.value.code == 'batch_too_large'


def test_duplicate_hash_in_same_class_returns_duplicate_without_new_row(
    app, two_classes, jpeg_bytes
):
    """Identical source bytes are idempotent within one class."""
    class_id, _ = two_classes
    with app.app_context():
        first = StudentImageService.process_upload(
            class_id, uploaded_file('first.jpg', jpeg_bytes)
        )
        duplicate = StudentImageService.process_upload(
            class_id, uploaded_file('second.jpg', jpeg_bytes)
        )

        assert first['status'] == 'pending'
        assert duplicate['status'] == 'duplicate'
        assert StudentImage.query.filter_by(class_id=class_id).count() == 1


def test_duplicate_hash_is_allowed_in_another_class(app, two_classes, jpeg_bytes):
    """Content hashes do not deduplicate across the class privacy boundary."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        first = StudentImageService.process_upload(
            first_class_id, uploaded_file('first.jpg', jpeg_bytes)
        )
        second = StudentImageService.process_upload(
            second_class_id, uploaded_file('second.jpg', jpeg_bytes)
        )

        assert first['status'] == 'pending'
        assert second['status'] == 'pending'
        assert StudentImage.query.count() == 2


def test_duplicate_integrity_race_returns_existing_row(
    app, two_classes, jpeg_bytes, monkeypatch
):
    """A stale duplicate precheck recovers from the database uniqueness race."""
    class_id, _ = two_classes
    content_hash = hashlib.sha256(jpeg_bytes).hexdigest()
    with app.app_context():
        existing = StudentImage(
            class_id=class_id,
            original_filename='existing.jpg',
            storage_filename='existing.jpg',
            match_status='pending',
            mime_type='image/jpeg',
            file_size=1,
            content_hash=content_hash,
        )
        db.session.add(existing)
        db.session.commit()
        existing_id = existing.id

        actual_find_duplicate = StudentImageRepository.find_duplicate
        call_count = 0

        def stale_then_current(target_class_id: int, target_hash: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None
            return actual_find_duplicate(target_class_id, target_hash)

        monkeypatch.setattr(
            StudentImageRepository,
            'find_duplicate',
            staticmethod(stale_then_current),
        )

        result = StudentImageService.process_upload(
            class_id, uploaded_file('racing.jpg', jpeg_bytes)
        )

        assert result['status'] == 'duplicate'
        assert result['image']['id'] == existing_id
        assert StudentImage.query.filter_by(class_id=class_id).count() == 1
        class_folder = Path(app.config['STUDENT_IMAGE_FOLDER']) / str(class_id)
        assert not any(class_folder.iterdir())


def test_preferred_student_upload_binds_immediately_within_class(
    app, two_classes, jpeg_bytes
):
    """A student-specific upload bypasses filename matching inside its class."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, 'PREFERRED001', 'Preferred Student')
        result = StudentImageService.process_upload(
            class_id,
            uploaded_file('portrait.jpg', jpeg_bytes),
            preferred_student_id=student.id,
        )

        assert result['status'] == 'matched'
        assert result['image']['student_id'] == student.id


def test_preferred_student_from_another_class_is_rejected(app, two_classes, jpeg_bytes):
    """Preferred binding cannot cross the class boundary."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        student = add_student(second_class_id, 'CROSS002', 'Other Class')
        with pytest.raises(ImageProcessingError) as error:
            StudentImageService.process_upload(
                first_class_id,
                uploaded_file('portrait.jpg', jpeg_bytes),
                preferred_student_id=student.id,
            )

        assert error.value.code == 'student_not_found'
        assert StudentImage.query.filter_by(class_id=first_class_id).count() == 0


def test_cross_class_preference_is_rejected_before_duplicate_shortcut(
    app, two_classes, jpeg_bytes
):
    """A duplicate hash cannot bypass validation of the requested student scope."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        StudentImageService.process_upload(
            first_class_id, uploaded_file('existing.jpg', jpeg_bytes)
        )
        foreign_student = add_student(second_class_id, 'CROSS003', 'Foreign Student')

        with pytest.raises(ImageProcessingError) as error:
            StudentImageService.process_upload(
                first_class_id,
                uploaded_file('duplicate.jpg', jpeg_bytes),
                preferred_student_id=foreign_student.id,
            )

        assert error.value.code == 'student_not_found'


def test_replacing_student_photo_keeps_one_row_and_deletes_old_file(app, two_classes):
    """Successful replacement swaps metadata and removes the obsolete file afterward."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, 'REPLACE001', 'Replace Student')
        first = StudentImageService.process_upload(
            class_id,
            uploaded_file('first.jpg', jpeg_with_color((10, 20, 30))),
            preferred_student_id=student.id,
        )
        image = db.session.get(StudentImage, first['image']['id'])
        old_path = StudentImageService.get_storage_path(image)

        second = StudentImageService.process_upload(
            class_id,
            uploaded_file('second.jpg', jpeg_with_color((40, 50, 60))),
            preferred_student_id=student.id,
        )
        replacement = db.session.get(StudentImage, second['image']['id'])

        assert replacement.id == image.id
        assert StudentImage.query.filter_by(student_id=student.id).count() == 1
        assert not old_path.exists()
        assert StudentImageService.get_storage_path(replacement).exists()


def test_database_failure_retains_old_replacement_file_and_row(
    app, two_classes, monkeypatch
):
    """A failed commit rolls metadata back and cleans the staged replacement only."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, 'ROLLBACK001', 'Rollback Student')
        first = StudentImageService.process_upload(
            class_id,
            uploaded_file('first.jpg', jpeg_with_color((10, 10, 10))),
            preferred_student_id=student.id,
        )
        image_id = first['image']['id']
        image = db.session.get(StudentImage, image_id)
        assert image.student_id == student.id
        old_filename = image.storage_filename
        old_path = StudentImageService.get_storage_path(image)

        def fail_commit() -> None:
            raise RuntimeError('simulated database failure')

        monkeypatch.setattr(db.session, 'commit', fail_commit)
        with pytest.raises(RuntimeError, match='simulated database failure'):
            StudentImageService.process_upload(
                class_id,
                uploaded_file('second.jpg', jpeg_with_color((20, 20, 20))),
                preferred_student_id=student.id,
            )

        persisted = db.session.get(StudentImage, image_id)
        assert persisted.storage_filename == old_filename
        assert old_path.exists()
        assert [path.name for path in old_path.parent.iterdir()] == [old_filename]


def test_bind_over_existing_target_requires_confirmation(app, two_classes):
    """Manual binding refuses to displace a target portrait without confirmation."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, 'BIND001', 'Bind Target')
        source = pending_image(class_id, 'source.jpg', jpeg_with_color((1, 1, 1)))
        target = pending_image(class_id, 'target.jpg', jpeg_with_color((2, 2, 2)))
        target.student_id = student.id
        target.match_status = 'matched'
        db.session.commit()

        with pytest.raises(ImageProcessingError) as error:
            StudentImageService.bind_image(class_id, source.id, student.id)

        assert error.value.code == 'binding_conflict'
        assert StudentImageRepository.get_for_student(student.id, class_id).id == target.id


def test_confirmed_bind_replaces_target_image(app, two_classes):
    """Confirmed binding keeps the source file and removes the displaced target."""
    class_id, _ = two_classes
    with app.app_context():
        student = add_student(class_id, 'BIND002', 'Confirmed Target')
        source = pending_image(class_id, 'source.jpg', jpeg_with_color((3, 3, 3)))
        target = pending_image(class_id, 'target.jpg', jpeg_with_color((4, 4, 4)))
        source_path = StudentImageService.get_storage_path(source)
        target_path = StudentImageService.get_storage_path(target)
        target.student_id = student.id
        target.match_status = 'matched'
        db.session.commit()

        result = StudentImageService.bind_image(
            class_id, source.id, student.id, confirm_replace=True
        )

        assert result['id'] == source.id
        assert result['student_id'] == student.id
        assert db.session.get(StudentImage, target.id) is None
        assert source_path.exists()
        assert not target_path.exists()


def test_confirmed_rebind_leaves_source_student_without_image(app, two_classes):
    """Moving an assigned source image clears its former student's one-image relation."""
    class_id, _ = two_classes
    with app.app_context():
        former = add_student(class_id, 'REBIND001', 'Former Student')
        destination = add_student(class_id, 'REBIND002', 'Destination Student')
        source = pending_image(class_id, 'source.jpg', jpeg_with_color((5, 5, 5)))
        source.student_id = former.id
        source.match_status = 'matched'
        db.session.commit()

        StudentImageService.bind_image(
            class_id, source.id, destination.id, confirm_replace=True
        )

        assert StudentImageRepository.get_for_student(former.id, class_id) is None
        assert StudentImageRepository.get_for_student(destination.id, class_id).id == source.id


def test_delete_image_removes_metadata_and_file(app, two_classes, jpeg_bytes):
    """Deletion removes both protected media and its class-scoped row."""
    class_id, _ = two_classes
    with app.app_context():
        image = pending_image(class_id, 'delete.jpg', jpeg_bytes)
        image_path = StudentImageService.get_storage_path(image)

        deleted = StudentImageService.delete_image(class_id, image.id)

        assert deleted is True
        assert db.session.get(StudentImage, image.id) is None
        assert not image_path.exists()


def test_rematch_pending_does_not_scan_or_mutate_another_class(app, two_classes):
    """Pending rematching is strictly scoped to the supplied class."""
    first_class_id, second_class_id = two_classes
    with app.app_context():
        first_image = pending_image(
            first_class_id, '01-Alice.jpg', jpeg_with_color((6, 6, 6))
        )
        second_image = pending_image(
            second_class_id, '02-Bob.jpg', jpeg_with_color((7, 7, 7))
        )
        alice = add_student(first_class_id, 'CLASS1001', 'Alice')
        add_student(second_class_id, 'CLASS2002', 'Bob')

        result = StudentImageService.rematch_pending(first_class_id)

        assert result == {'checked_count': 1, 'matched_count': 1, 'remaining_count': 0}
        assert db.session.get(StudentImage, first_image.id).student_id == alice.id
        untouched = db.session.get(StudentImage, second_image.id)
        assert untouched.student_id is None
        assert untouched.match_status == 'pending'
