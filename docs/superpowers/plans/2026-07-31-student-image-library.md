# Student Image Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a class-scoped student image library that parses existing filename conventions, automatically links photos during upload or later student imports, supports manual replacement, and displays the same portrait-sized avatar on student profile and overview pages.

**Architecture:** Store normalized image files under `uploads/student_images/<class_id>/` and persist searchable metadata in a new `student_image` table. Keep parsing, matching, file validation, replacement, and rematching in `StudentImageService`; controllers only enforce the active-class boundary and translate service results to HTTP. Existing Excel importers remain plugin-independent and call one class-scoped rematch hook after successful imports.

**Tech Stack:** Flask 3, Flask-SQLAlchemy/SQLAlchemy 2, MySQL 8 with SQLite tests, Pillow, Bootstrap 5/AdminLTE, jQuery, pytest.

## Global Constraints

- All automatic and manual matching is strictly scoped to the active `class_id`; never query candidates across classes.
- `01-李少飞.jpg` matches only by active class + student number suffix `01` + exact normalized name `李少飞`.
- `202306142001江承阳.jpg` matches only by active class + exact full student number + exact normalized name.
- A student has at most one current image; a successful replacement deletes the previous file and does not retain history.
- Deleting a student keeps the image record in the original class and returns it to `pending`.
- Supported source images are JPG, JPEG, PNG, and WebP; ZIP is a transport container only.
- Maximum source image size is 5 MB, maximum batch count is 200 images, and maximum request size is 100 MB.
- Normalize valid uploads to JPEG, apply EXIF orientation, and constrain the longest edge to 1024 pixels without face detection or automatic face cropping.
- Images are served only through authenticated, active-class-checked media routes with `Cache-Control: private`.
- Pages read persisted metadata only; filename matching and image processing never run during page rendering.
- Python additions require type annotations and docstrings; keep each function under 150 lines.

## File Structure

### New files

- `models/student_image.py` — `StudentImage` ORM model and serialization.
- `repositories/student_image_repo.py` — class-scoped persistence queries and one-to-one binding primitives.
- `services/student_image_service.py` — parsing, matching, normalization, ZIP handling, replacement, rematching, and filesystem consistency.
- `controllers/student_image_controller.py` — image-library page, JSON endpoints, and protected media response.
- `templates/student_image/index.html` — paginated image library and batch results UI.
- `templates/student/_avatar_modal.html` — shared image-library chooser and local-upload modal.
- `static/js/student_avatar.js` — shared avatar selection, confirmation, upload, and refresh behavior.
- `static/img/default-avatar.svg` — generic fallback returned when persisted media is missing.
- `tests/test_student_image_model.py` — schema, constraints, serialization, and repository tests.
- `tests/test_student_image_matching.py` — filename parsing and class-scoped match tests.
- `tests/test_student_image_service.py` — file validation, normalization, ZIP, duplicate, replacement, and rematch tests.
- `tests/test_student_image_api.py` — authentication, class isolation, upload, bind, delete, and media tests.
- `tests/test_student_image_pages.py` — image-library and student-page markup/API contract tests.

### Modified files

- `requirements.txt` — add Pillow.
- `config.py` — image storage and upload limits.
- `app.py` — create image directory and register blueprint.
- `models/__init__.py` — export `StudentImage`.
- `models/student.py` — one-to-one image relationship and `avatar_url` serialization.
- `repositories/__init__.py` — export `StudentImageRepository`.
- `repositories/student_repo.py` — include `avatar_url` in full-overview data and unlink images during student deletion.
- `controllers/__init__.py` — export image blueprint.
- `controllers/import_controller.py` — invoke class-scoped pending-image rematch after successful imports.
- `templates/base.html` — add image-library navigation.
- `templates/student/detail.html` — portrait area and shared avatar chooser.
- `templates/student/overview.html` — `132 × 166` portrait header and shared avatar chooser.
- `tests/conftest.py` — isolate image storage in `tmp_path` and provide image bytes fixture.

---

### Task 1: Image Configuration, Model, and Repository

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py:35-45, Config`
- Modify: `app.py:ensure_directories`
- Create: `models/student_image.py`
- Modify: `models/student.py:Student relationships`
- Modify: `models/__init__.py`
- Create: `repositories/student_image_repo.py`
- Modify: `repositories/__init__.py`
- Modify: `tests/conftest.py:app fixture`
- Create: `tests/test_student_image_model.py`

**Interfaces:**
- Produces: `StudentImage` with `media_url: str`, `to_dict() -> dict`, and nullable unique `student_id`.
- Produces: `StudentImageRepository.get_by_id(image_id: int, class_id: int) -> Optional[StudentImage]`.
- Produces: `StudentImageRepository.get_for_student(student_id: int, class_id: int) -> Optional[StudentImage]`.
- Produces: `StudentImageRepository.list_page(class_id: int, status: Optional[str], keyword: str, page: int, per_page: int)`.
- Produces: test config key `STUDENT_IMAGE_FOLDER` pointing inside each test's `tmp_path`.

- [ ] **Step 1: Add Pillow and image configuration tests**

Add tests that assert the application creates an isolated student image directory and that schema creation includes the new table:

```python
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
```

- [ ] **Step 2: Run the model tests to verify they fail**

Run: `pytest tests/test_student_image_model.py -v`

Expected: FAIL because `student_image` and `STUDENT_IMAGE_FOLDER` do not exist.

- [ ] **Step 3: Add configuration and dependency declarations**

Add `Pillow==11.1.0` to `requirements.txt`. In `config.py`, define and expose:

```python
STUDENT_IMAGE_FOLDER = UPLOAD_FOLDER / 'student_images'
STUDENT_IMAGE_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
STUDENT_IMAGE_MAX_FILE_SIZE = 5 * 1024 * 1024
STUDENT_IMAGE_MAX_BATCH_FILES = 200
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
```

Add the values to `Config`, and append `app.config['STUDENT_IMAGE_FOLDER']` to `ensure_directories()`.

- [ ] **Step 4: Create the ORM model**

Implement `StudentImage` with indexed `class_id`, unique nullable `student_id`, unique `storage_filename`, and the metadata from the design. Keep status as `String(20)` and define:

```python
@property
def media_url(self) -> str:
    return f'/media/student-images/{self.id}'


def to_dict(self) -> dict:
    return {
        'id': self.id,
        'class_id': self.class_id,
        'student_id': self.student_id,
        'student_no': self.student.student_no if self.student else None,
        'student_name': self.student.name if self.student else None,
        'original_filename': self.original_filename,
        'parsed_student_no': self.parsed_student_no,
        'number_match_type': self.number_match_type,
        'parsed_name': self.parsed_name,
        'match_status': self.match_status,
        'match_message': self.match_message,
        'mime_type': self.mime_type,
        'file_size': self.file_size,
        'avatar_url': self.media_url,
    }
```

Add `Student.image = relationship('StudentImage', back_populates='student', uselist=False, lazy=True)` and the inverse relationship without delete cascade.

- [ ] **Step 5: Implement class-scoped repository primitives**

Implement exact class filters in every query:

```python
class StudentImageRepository:
    @staticmethod
    def get_by_id(image_id: int, class_id: int) -> Optional[StudentImage]:
        return StudentImage.query.filter_by(id=image_id, class_id=class_id).first()

    @staticmethod
    def get_for_student(student_id: int, class_id: int) -> Optional[StudentImage]:
        return StudentImage.query.filter_by(student_id=student_id, class_id=class_id).first()

    @staticmethod
    def find_duplicate(class_id: int, content_hash: str) -> Optional[StudentImage]:
        return StudentImage.query.filter_by(class_id=class_id, content_hash=content_hash).first()
```

`list_page()` must cap `per_page` at 100, filter status only when supplied, and apply escaped `LIKE` search to original filename, parsed name, parsed number, student name, and student number.

- [ ] **Step 6: Add uniqueness, nullability, class-scoping, and serialization tests**

Cover two pending rows with `student_id=None`, rejection of two rows bound to the same student, same student number suffix in different classes, and `to_dict()['avatar_url']`.

- [ ] **Step 7: Run focused tests**

Run: `pytest tests/test_student_image_model.py -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit the task**

```bash
git add requirements.txt config.py app.py models/student_image.py models/student.py models/__init__.py repositories/student_image_repo.py repositories/__init__.py tests/conftest.py tests/test_student_image_model.py
git commit -m "feat: add student image persistence"
```

---

### Task 2: Deterministic Filename Parsing and Class-Scoped Matching

**Files:**
- Create: `services/student_image_service.py`
- Create: `tests/test_student_image_matching.py`

**Interfaces:**
- Consumes: `Student`, `StudentImage`, and the active `class_id`.
- Produces: immutable `ParsedStudentImage(student_no: Optional[str], number_match_type: Optional[str], name: Optional[str])`.
- Produces: immutable `ImageMatchResult(status: str, student: Optional[Student], message: str)`.
- Produces: `StudentImageService.parse_filename(filename: str) -> ParsedStudentImage`.
- Produces: `StudentImageService.match_student(class_id: int, parsed: ParsedStudentImage) -> ImageMatchResult`.

- [ ] **Step 1: Write parser tests for both accepted conventions**

```python
def test_parse_suffix_and_name():
    parsed = StudentImageService.parse_filename('01-李少飞.jpg')
    assert parsed == ParsedStudentImage('01', 'suffix', '李少飞')


def test_parse_full_student_number_and_name():
    parsed = StudentImageService.parse_filename('202306142001江承阳.jpg')
    assert parsed == ParsedStudentImage('202306142001', 'full', '江承阳')
```

Also test whitespace around names, underscores around the name, unsupported patterns, and a valid image filename with no recognizable identity.

- [ ] **Step 2: Run parser tests to verify they fail**

Run: `pytest tests/test_student_image_matching.py -k parse -v`

Expected: FAIL because the service and dataclasses do not exist.

- [ ] **Step 3: Implement normalization and anchored regular expressions**

Use only anchored patterns:

```python
SUFFIX_PATTERN = re.compile(r'^(?P<number>\d{2})-(?P<name>.+)$')
FULL_PATTERN = re.compile(r'^(?P<number>\d{3,})(?P<name>[^\d].*)$')


def _normalize_name(value: str) -> str:
    return value.strip().strip('_- ').strip()
```

Use `Path(filename).stem`; do not perform fuzzy, substring, pinyin, or cross-class matching.

- [ ] **Step 4: Write class-isolation and conflict tests**

Create students so that the same `01` suffix and same name exist in two classes. Assert the current class returns exactly its own student. Also assert:

- one matching suffix + exact name returns `matched`;
- suffix match with a different name returns `conflict`;
- full number with different name returns `conflict`;
- no current-class student returns `pending`;
- multiple same-class candidates return `conflict`;
- unparseable filename returns `pending` without a student.

- [ ] **Step 5: Run matching tests to verify they fail**

Run: `pytest tests/test_student_image_matching.py -k match -v`

Expected: FAIL because `match_student()` is absent.

- [ ] **Step 6: Implement the exact match algorithm**

Implement suffix matching with both SQL suffix and exact normalized name predicates inside the current class. Separately detect contradictory number/name evidence to produce a clear conflict message:

```python
def match_student(class_id: int, parsed: ParsedStudentImage) -> ImageMatchResult:
    if not parsed.student_no or not parsed.name:
        return ImageMatchResult('pending', None, '文件名无法提取完整匹配信息')
    candidates = _query_exact_candidates(class_id, parsed)
    if len(candidates) == 1:
        return ImageMatchResult('matched', candidates[0], '已自动关联')
    if len(candidates) > 1:
        return ImageMatchResult('conflict', None, '当前班级存在多个候选学生')
    if _number_or_name_conflicts(class_id, parsed):
        return ImageMatchResult('conflict', None, '学号信息与姓名不一致')
    return ImageMatchResult('pending', None, '当前班级尚无匹配学生')
```

- [ ] **Step 7: Run all matching tests**

Run: `pytest tests/test_student_image_matching.py -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit the task**

```bash
git add services/student_image_service.py tests/test_student_image_matching.py
git commit -m "feat: match student images within classes"
```

---

### Task 3: Image Validation, Normalization, Batch Upload, and Replacement

**Files:**
- Modify: `services/student_image_service.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_student_image_service.py`

**Interfaces:**
- Consumes: `StudentImageRepository`, `parse_filename()`, and `match_student()`.
- Produces: `ImageProcessingError(code: str, message: str)`.
- Produces: `StudentImageService.process_upload(class_id: int, file: FileStorage, preferred_student_id: Optional[int] = None) -> dict`.
- Produces: `StudentImageService.process_batch(class_id: int, files: Sequence[FileStorage]) -> dict`.
- Produces: `StudentImageService.bind_image(class_id: int, image_id: int, student_id: int, confirm_replace: bool = False) -> dict`.
- Produces: `StudentImageService.delete_image(class_id: int, image_id: int) -> bool`.
- Produces: `StudentImageService.rematch_pending(class_id: int) -> dict`.
- Produces: `StudentImageService.get_storage_path(image: StudentImage) -> Path`.

- [ ] **Step 1: Add a reusable valid-image fixture and failing validation tests**

In `tests/conftest.py`, provide JPEG bytes without filesystem dependencies outside `tmp_path`:

```python
@pytest.fixture()
def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new('RGB', (1200, 800), color=(80, 120, 160)).save(buffer, format='JPEG')
    return buffer.getvalue()
```

Test invalid bytes disguised as JPG, unsupported extension, a source over 5 MB, and a valid JPEG that becomes a real normalized JPEG no larger than 1024 pixels on its longest edge.

- [ ] **Step 2: Run validation tests to verify they fail**

Run: `pytest tests/test_student_image_service.py -k "validation or normalize" -v`

Expected: FAIL because upload processing is not implemented.

- [ ] **Step 3: Implement safe normalization to a temporary file**

Read at most `STUDENT_IMAGE_MAX_FILE_SIZE + 1` bytes, verify with Pillow, reopen, apply `ImageOps.exif_transpose`, convert to RGB, call `thumbnail((1024, 1024))`, and save JPEG quality 85. Generate storage names with `uuid4().hex + '.jpg'` under the resolved class directory.

Reject an input when its resolved destination is not inside the configured image root.

- [ ] **Step 4: Write failing batch, duplicate, and ZIP safety tests**

Cover:

- two valid files produce two per-file results;
- one invalid file does not roll back a valid sibling;
- more than 200 entries is rejected before processing;
- a ZIP entry named `../escape.jpg` is rejected;
- a nested ZIP is rejected;
- expanded ZIP content is bounded by the 100 MB request limit;
- duplicate `class_id + SHA-256` returns `duplicate` and creates no row;
- the same bytes in another class are allowed.

- [ ] **Step 5: Implement batch and ZIP entry iteration**

Treat regular files and ZIP entries as a common stream of `(display_filename, binary_stream)`. Use `zipfile.Path`/`ZipInfo` checks and never call `extractall()`. Aggregate this exact response shape:

```python
{
    'success': failed_count == 0,
    'total_files': total,
    'matched_count': matched,
    'pending_count': pending,
    'conflict_count': conflicts,
    'duplicate_count': duplicates,
    'failed_count': failed,
    'results': per_file_results,
}
```

- [ ] **Step 6: Write failing replacement, bind, delete, and rematch tests**

Assert:

- upload with `preferred_student_id` immediately binds within the same class;
- a preferred student from another class is rejected;
- replacing an existing student's photo leaves one database row and deletes the old file;
- a simulated database failure retains the old file and row;
- binding over an existing target without confirmation raises a conflict;
- confirmed bind replaces the target image;
- confirmed rebind from another student leaves the source student without an image;
- delete removes metadata and file;
- `rematch_pending(class_id)` does not scan or mutate another class.

- [ ] **Step 7: Implement transactional replacement and rematching**

Write the new normalized file to `*.tmp`, flush metadata changes, atomically move to the final path with `os.replace`, commit, and only then delete the old file. On pre-commit failure, roll back and remove the temporary/new file while leaving the old image intact.

`rematch_pending()` must query only `pending` and `conflict` rows for the supplied class and return:

```python
{'checked_count': checked, 'matched_count': matched, 'remaining_count': remaining}
```

- [ ] **Step 8: Run all service tests**

Run: `pytest tests/test_student_image_service.py tests/test_student_image_matching.py -v`

Expected: all tests PASS.

- [ ] **Step 9: Commit the task**

```bash
git add services/student_image_service.py tests/conftest.py tests/test_student_image_service.py
git commit -m "feat: process and replace student images"
```

---

### Task 4: Protected Image Library API and Media Delivery

**Files:**
- Create: `controllers/student_image_controller.py`
- Modify: `controllers/__init__.py`
- Modify: `app.py:imports and register_blueprints`
- Create: `static/img/default-avatar.svg`
- Create: `tests/test_student_image_api.py`

**Interfaces:**
- Consumes: all public `StudentImageService` operations from Task 3.
- Produces: blueprint `student_image_bp = Blueprint('student_image', __name__)`.
- Produces: endpoints specified in the approved design.

- [ ] **Step 1: Write failing authentication and class-isolation API tests**

Test anonymous access, logged-in access without an active class, cross-class IDs returning 404, and a valid active-class list. Include page and API paths in the existing class-guard parametrization where appropriate.

- [ ] **Step 2: Run guard tests to verify they fail**

Run: `pytest tests/test_student_image_api.py -k "auth or class" -v`

Expected: FAIL because the blueprint is not registered.

- [ ] **Step 3: Register the blueprint and list/page routes**

Implement:

```python
@student_image_bp.get('/student-images')
@require_active_class
def index():
    return render_template('student_image/index.html')


@student_image_bp.get('/api/student-images')
@require_active_class
def list_images():
    class_id = get_active_class_id()
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 24, type=int), 1), 100)
    result = StudentImageRepository.list_page(
        class_id, request.args.get('status'), request.args.get('keyword', '').strip(),
        page, per_page,
    )
    return jsonify({
        'items': [item.to_dict() for item in result.items],
        'page': result.page,
        'per_page': result.per_page,
        'total': result.total,
        'pages': result.pages,
    })
```

Return 400 for an unknown status instead of silently ignoring it.

- [ ] **Step 4: Write failing upload, bind, delete, and media tests**

Test multipart fields named `files`, a ZIP upload, per-file results, 409 confirmation, successful bind, confirmed replacement, deletion, correct JPEG MIME, private caching, ETag response, and a missing disk file returning the default avatar response plus a logged error.

- [ ] **Step 5: Implement mutation routes and error translation**

Implement exact routes:

```python
POST   /api/student-images/batch
POST   /api/student-images/<int:image_id>/bind
DELETE /api/student-images/<int:image_id>
POST   /api/student/<int:student_id>/image
GET    /media/student-images/<int:image_id>
```

Translate `not_found` to 404, validation to 400, replacement confirmation to 409, and unexpected failures to 500 with `current_app.logger.exception('Student image request failed for class %s', class_id)`.

For media delivery, resolve the database row by active class first, then call `send_file(path, mimetype='image/jpeg', conditional=True, max_age=3600)` and override `Cache-Control` to `private, max-age=3600`. If the database row exists but its file is missing, log the record ID and return `static/img/default-avatar.svg` through this same protected route.

- [ ] **Step 6: Run API tests**

Run: `pytest tests/test_student_image_api.py -v`

Expected: all tests PASS.

- [ ] **Step 7: Run existing authentication and class-isolation tests**

Run: `pytest tests/test_auth.py tests/test_class_isolation.py -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit the task**

```bash
git add controllers/student_image_controller.py controllers/__init__.py app.py static/img/default-avatar.svg tests/test_student_image_api.py tests/test_class_isolation.py
git commit -m "feat: expose protected student image APIs"
```

---

### Task 5: Student Import Rematching and Deletion Preservation

**Files:**
- Modify: `controllers/import_controller.py:upload and folder success paths`
- Modify: `repositories/student_repo.py:delete`
- Modify: `tests/test_import_compatibility.py`
- Modify: `tests/test_student_deletion.py`

**Interfaces:**
- Consumes: `StudentImageService.rematch_pending(class_id: int) -> dict`.
- Produces: successful import responses with `image_matching` summary.
- Produces: student deletion behavior that keeps the image row as `pending` with `student_id=None`.

- [ ] **Step 1: Write a failing import-rematch test**

Create a pending `01-李少飞.jpg` image in class A, import/create the matching student in class A through the existing import orchestration, and assert:

```python
assert response['image_matching']['matched_count'] == 1
assert StudentImage.query.one().student_id == imported_student.id
```

Add a second pending image in class B and assert it remains unchanged.

- [ ] **Step 2: Run the import test to verify it fails**

Run: `pytest tests/test_import_compatibility.py -k image -v`

Expected: FAIL because import responses have no `image_matching` hook.

- [ ] **Step 3: Add one rematch hook after successful import orchestration**

After any successful file in `/api/import/upload`, and after any successful file in folder import, call the service once per request:

```python
if any(item.get('success') for item in results):
    try:
        response['image_matching'] = StudentImageService.rematch_pending(target_class.id)
    except Exception as exc:
        current_app.logger.exception('Student image rematch failed for class %s', target_class.id)
        response['image_matching_warning'] = f'学生数据导入成功，但头像自动关联失败：{exc}'
```

Do not call this inside `BaseImporter` or any concrete Rain Classroom/Educoder importer.

- [ ] **Step 4: Write a failing student-deletion preservation test**

Bind a real stored image to the student, delete the student through `DELETE /api/student/<id>`, and assert the image file still exists while:

```python
assert image.student_id is None
assert image.match_status == 'pending'
assert image.match_message == '学生已删除，等待重新关联'
```

- [ ] **Step 5: Run the deletion test to verify it fails**

Run: `pytest tests/test_student_deletion.py -k image -v`

Expected: FAIL because the current repository deletion does not unlink `StudentImage`.

- [ ] **Step 6: Unlink images inside the existing deletion transaction**

Before deleting `Student`, update the bound image record instead of deleting it:

```python
image = StudentImage.query.filter_by(student_id=student.id, class_id=class_id).first()
if image:
    image.student_id = None
    image.match_status = 'pending'
    image.match_message = '学生已删除，等待重新关联'
```

Keep this in the same database transaction as deletion of behavior, practice, mastery, warning, assignment, and student rows.

- [ ] **Step 7: Run focused integration tests**

Run: `pytest tests/test_import_compatibility.py tests/test_student_deletion.py -v`

Expected: all tests PASS.

- [ ] **Step 8: Commit the task**

```bash
git add controllers/import_controller.py repositories/student_repo.py tests/test_import_compatibility.py tests/test_student_deletion.py
git commit -m "feat: rematch images after student imports"
```

---

### Task 6: Image Library Page and Navigation

**Files:**
- Create: `templates/student_image/index.html`
- Modify: `templates/base.html:sidebar navigation`
- Create: `tests/test_student_image_pages.py`

**Interfaces:**
- Consumes: `GET /api/student-images`, `POST /api/student-images/batch`, bind, and delete endpoints.
- Produces: page selectors `#image-grid`, `#image-upload-input`, `#zip-upload-input`, `#status-filter`, `#image-search`, and `#batch-result-modal`.

- [ ] **Step 1: Write a failing page-contract test**

After login and class selection, request `/student-images` and assert the response contains:

```python
for marker in (
    'id="image-grid"', 'id="image-upload-input"', 'id="zip-upload-input"',
    'id="status-filter"', 'id="image-search"', 'id="batch-result-modal"',
    '/api/student-images/batch',
):
    assert marker in page
```

Also assert the sidebar contains the image-library link and active-state expression.

- [ ] **Step 2: Run the page test to verify it fails**

Run: `pytest tests/test_student_image_pages.py -k library -v`

Expected: FAIL because the template does not exist.

- [ ] **Step 3: Build the library layout**

Create an AdminLTE/Bootstrap page with:

- four summary boxes: total, matched, pending, conflict;
- multi-image input and ZIP input;
- keyword and status controls;
- 24-card paginated grid;
- escaped original filename, parsed identity, bound student, status badge, and actions;
- a batch-result modal with one row per source file;
- bind/replace confirmation modal and destructive delete confirmation.

Do not embed image binary or filesystem paths. Set every image `src` from the API's `avatar_url`.

- [ ] **Step 4: Implement page-side loading and mutations**

Use existing jQuery and global CSRF setup. Keep one state object:

```javascript
var imageLibraryState = { page: 1, perPage: 24, status: '', keyword: '' };
```

Use `FormData` with repeated `files` values. Escape all server text before inserting HTML. On 409, show the server confirmation text and retry with `confirm_replace: true` only after user confirmation.

- [ ] **Step 5: Add sidebar navigation**

Add a `student_image.index` link with an image icon immediately after the student profile navigation item. Its active state must check `request.endpoint` starts with `student_image.`.

- [ ] **Step 6: Run page and API tests**

Run: `pytest tests/test_student_image_pages.py tests/test_student_image_api.py -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit the task**

```bash
git add templates/student_image/index.html templates/base.html tests/test_student_image_pages.py
git commit -m "feat: add student image library page"
```

---

### Task 7: Student Profile and Overview Avatar Integration

**Files:**
- Modify: `models/student.py:to_dict`
- Modify: `repositories/student_repo.py:get_full_overview`
- Modify: `templates/student/detail.html`
- Modify: `templates/student/overview.html`
- Create: `templates/student/_avatar_modal.html`
- Create: `static/js/student_avatar.js`
- Modify: `tests/test_student_image_pages.py`
- Modify: `tests/test_class_isolation.py`

**Interfaces:**
- Consumes: `Student.image`, `StudentImage.media_url`, list/bind/single-upload APIs.
- Produces: `avatar_url: Optional[str]` in `/api/student/<id>` and `/api/student/<id>/overview` under `basic`.
- Produces: shared `StudentAvatar.mount({studentId, avatarSelector, defaultSelector})` behavior and modal selectors `.avatar-library-modal`, `.avatar-library-grid`, and `.avatar-local-upload` on both pages.

- [ ] **Step 1: Write failing API serialization tests**

Assert a student with an image returns the protected URL from both APIs, while a student without an image returns `null`:

```python
detail = client.get(f'/api/student/{student_id}').get_json()
overview = client.get(f'/api/student/{student_id}/overview').get_json()
assert detail['avatar_url'] == f'/media/student-images/{image_id}'
assert overview['basic']['avatar_url'] == f'/media/student-images/{image_id}'
```

- [ ] **Step 2: Run serialization tests to verify they fail**

Run: `pytest tests/test_student_image_pages.py -k avatar_url -v`

Expected: FAIL because the APIs do not return `avatar_url`.

- [ ] **Step 3: Add persisted avatar URLs to student dictionaries**

In `Student.to_dict()` add:

```python
'avatar_url': self.image.media_url if self.image else None,
```

In `StudentRepository.get_full_overview()['basic']`, add the same field. Do not inspect directories or rerun matching in either path.

- [ ] **Step 4: Write failing profile and overview markup tests**

Assert both pages include a `132 × 166` avatar element, default-avatar element, “从图像库选择” and “本地上传” actions, include `student/_avatar_modal.html`, and load `static/js/student_avatar.js`. Assert the overview basic card uses the three-column portrait/info/actions structure from the approved visual design.

- [ ] **Step 5: Run markup tests to verify they fail**

Run: `pytest tests/test_student_image_pages.py -k "profile or overview" -v`

Expected: FAIL because the avatar UI is absent.

- [ ] **Step 6: Integrate the portrait into the student profile page**

In the existing basic-info card, render a fixed portrait region:

```html
<img id="student-avatar" class="student-avatar d-none" alt="学生照片">
<div id="student-avatar-default" class="student-avatar-default" aria-label="默认头像">--</div>
```

Use CSS width `132px`, height `166px`, and `object-fit: cover`. When the detail API resolves, use `data.avatar_url` or show the first character of `data.name`. Add chooser and local-upload actions below the image.

- [ ] **Step 7: Integrate the same portrait into the overview header**

Replace the table-only basic card with a responsive three-column header: `160px` portrait column, flexible information column, and action column. Use the identical `132 × 166` portrait class. Below 768px, stack actions without changing the downstream knowledge, practice, warning, or assignment tables.

- [ ] **Step 8: Implement the shared chooser partial and JavaScript module**

Create the modal once in `templates/student/_avatar_modal.html` and include it from both pages. Expose one browser module from `static/js/student_avatar.js`:

```javascript
window.StudentAvatar = {
    mount: function (options) {
        // options: studentId, avatarSelector, defaultSelector, nameSelector
    }
};
```

The shared implementation must:

- load only the active class via `/api/student-images`;
- bind the selected image to the current `studentId`;
- retry only after explicit 409 confirmation;
- upload one local file to `/api/student/<studentId>/image`;
- update the portrait immediately from the returned `avatar_url` with a cache-busting query using the returned image ID or update timestamp;
- never accept a client-provided class ID.

Call this once after each page defines its existing `studentId` variable:

```javascript
StudentAvatar.mount({
    studentId: studentId,
    avatarSelector: '#student-avatar',
    defaultSelector: '#student-avatar-default',
    nameSelector: '#student-name'
});
```

- [ ] **Step 9: Run student-page and class-isolation tests**

Run: `pytest tests/test_student_image_pages.py tests/test_class_isolation.py -v`

Expected: all tests PASS.

- [ ] **Step 10: Commit the task**

```bash
git add models/student.py repositories/student_repo.py templates/student/detail.html templates/student/overview.html templates/student/_avatar_modal.html static/js/student_avatar.js tests/test_student_image_pages.py tests/test_class_isolation.py
git commit -m "feat: show avatars on student pages"
```

---

### Task 8: Full Regression, Security Verification, and Release Readiness

**Files:**
- Modify if required by verified failures only: files introduced or explicitly modified in Tasks 1–7
- Verify: `docs/superpowers/specs/2026-07-31-student-image-library-design.md`

**Interfaces:**
- Consumes: complete feature from Tasks 1–7.
- Produces: a verified implementation satisfying every acceptance criterion in the approved design.

- [ ] **Step 1: Install the pinned dependency in the active environment**

Run: `python -m pip install -r requirements.txt`

Expected: exit code 0 and Pillow 11.1.0 installed.

- [ ] **Step 2: Run focused feature tests**

Run:

```bash
pytest tests/test_student_image_model.py tests/test_student_image_matching.py tests/test_student_image_service.py tests/test_student_image_api.py tests/test_student_image_pages.py -v
```

Expected: all focused tests PASS.

- [ ] **Step 3: Run impacted regression tests**

Run:

```bash
pytest tests/test_import_compatibility.py tests/test_student_deletion.py tests/test_class_isolation.py tests/test_auth.py tests/test_schema.py -v
```

Expected: all impacted tests PASS.

- [ ] **Step 4: Run the full suite**

Run: `pytest -v`

Expected: zero failures and zero errors.

- [ ] **Step 5: Verify security boundaries with explicit test selection**

Run:

```bash
pytest tests/test_student_image_api.py -k "anonymous or active_class or cross_class or zip or media" -v
```

Expected: all selected tests PASS, demonstrating authentication, active-class isolation, archive/path safety, and protected media delivery.

- [ ] **Step 6: Perform a browser smoke test against a disposable class**

Start the application in the configured WSL environment. In one disposable class:

1. Upload `01-李少飞.jpg` and `202306142001江承阳.jpg` together.
2. Confirm unique students auto-link and per-file results are visible.
3. Upload a valid unmatched photo and confirm it appears as pending.
4. Import/create the matching student and confirm the pending photo auto-links.
5. Replace one avatar from local disk and confirm the library and both student pages update.
6. Confirm profile and overview portraits are both `132 × 166` and responsive.
7. Switch classes and confirm the other class cannot list, bind, or fetch these image IDs.
8. Delete a student and confirm their image remains pending in the original class.

- [ ] **Step 7: Check repository cleanliness and diff scope**

Run:

```bash
git status --short
git diff --check
git diff --stat HEAD~7..HEAD
```

Expected: no generated image files, ZIPs, uploads, logs, or unrelated edits are staged; no whitespace errors.

- [ ] **Step 8: Commit any verification-only corrections**

Only when Steps 2–7 expose a feature-scoped issue, inspect and interactively stage only the relevant hunks, then commit:

```bash
git add -p
git diff --cached --check
git commit -m "fix: harden student image integration"
```

If verification requires no correction, do not create an empty commit.
