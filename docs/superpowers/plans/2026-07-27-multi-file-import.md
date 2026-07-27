# Multi-File Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let teachers select and import multiple Excel files from both upload entry points with per-file results, preflight conflict protection, and one analysis run per batch.

**Architecture:** Extend the existing `/api/import/upload` endpoint to read repeated `file` multipart fields. Keep the existing response contract when exactly one file is submitted, and produce a folder-import-style aggregate response for multiple files. Both templates submit one multipart request and render either the legacy single result or the aggregate batch result.

**Tech Stack:** Python 3.9, Flask/Werkzeug multipart uploads, pytest, Jinja2, jQuery, Bootstrap/AdminLTE.

## Global Constraints

- Both the general import page and class detail page must support multi-select.
- Accept only `.xlsx` and `.xls` files.
- Preserve existing importers, database schema, file type detection, and folder-import behavior.
- Preserve the existing `/api/import/upload` response for a single file.
- Preflight all filenames for class mismatch before saving or importing any file.
- A file-level import failure must not stop later files in the same batch.
- Run class analysis at most once after a batch, and only if at least one file imported successfully.
- Escape every filename and server-provided message before inserting it into HTML.

---

### Task 1: Batch upload endpoint

**Files:**
- Modify: `controllers/import_controller.py:119-190`
- Test: `tests/test_class_imports.py`

**Interfaces:**
- Consumes: repeated multipart fields named `file`; existing `_get_target_class()`, `_class_mismatch()`, `allowed_file()`, `import_data()`, `calculate_file_hash()`, and `run_all_analysis()`.
- Produces: `_import_uploaded_file(file, target_class, import_type) -> dict`, `_build_batch_upload_response(results) -> dict`, and a multi-file response with `success`, `partial_success`, `total_files`, `imported_files`, `failed_files`, `total_imported_rows`, and `results`.

- [ ] **Step 1: Add failing tests for successful and partially successful batches**

Add tests using real multipart parsing and a stub only for the importer boundary:

```python
from io import BytesIO


def test_multi_file_upload_imports_in_order_and_analyzes_once(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    analyzed = []

    def fake_import(file_path, class_id, uploaded_by, **kwargs):
        imported.append(kwargs['original_filename'])
        return {
            'success': True,
            'import_type': 'test',
            'imported_count': 2,
        }

    monkeypatch.setattr('controllers.import_controller.import_data', fake_import)
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: analyzed.append(class_id) or {'summary': {'success': True}},
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': [
            (BytesIO(b'first'), 'rain-first.xlsx'),
            (BytesIO(b'second'), 'rain-second.xlsx'),
        ],
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert imported == ['rain-first.xlsx', 'rain-second.xlsx']
    assert analyzed == [first_id]
    assert payload['success'] is True
    assert payload['total_files'] == 2
    assert payload['imported_files'] == 2
    assert payload['failed_files'] == 0
    assert payload['total_imported_rows'] == 4
    assert [item['filename'] for item in payload['results']] == imported


def test_multi_file_upload_continues_after_file_failure(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []

    def fake_import(file_path, class_id, uploaded_by, **kwargs):
        filename = kwargs['original_filename']
        imported.append(filename)
        if filename == 'bad.xlsx':
            return {'success': False, 'message': '解析失败', 'imported_count': 0}
        return {'success': True, 'import_type': 'test', 'imported_count': 3}

    monkeypatch.setattr('controllers.import_controller.import_data', fake_import)
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: {'summary': {'success': True}},
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': [
            (BytesIO(b'bad'), 'bad.xlsx'),
            (BytesIO(b'good'), 'good.xlsx'),
        ],
    })

    payload = response.get_json()
    assert imported == ['bad.xlsx', 'good.xlsx']
    assert payload['success'] is False
    assert payload['partial_success'] is True
    assert payload['imported_files'] == 1
    assert payload['failed_files'] == 1
    assert payload['total_imported_rows'] == 3
```

- [ ] **Step 2: Run the new batch tests and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py -k "multi_file_upload_imports_in_order or multi_file_upload_continues" -v
```

Expected: FAIL because the endpoint reads only `request.files['file']` and returns a single-file payload.

- [ ] **Step 3: Add failing preflight and compatibility tests**

```python
def test_multi_file_class_mismatch_is_preflighted_before_any_import(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append(kwargs['original_filename']),
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': [
            (BytesIO(b'ok'), '青年1班-雨课堂.xlsx'),
            (BytesIO(b'conflict'), '青年2班-雨课堂.xlsx'),
        ],
    })

    payload = response.get_json()
    assert response.status_code == 409
    assert payload['error'] == 'class_name_mismatch'
    assert payload['conflicting_files'] == ['青年2班-雨课堂.xlsx']
    assert imported == []


def test_multi_file_upload_rejects_unsupported_format_before_any_import(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    imported = []
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: imported.append(kwargs['original_filename']),
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': [
            (BytesIO(b'ok'), 'ok.xlsx'),
            (BytesIO(b'bad'), 'bad.csv'),
        ],
    })

    assert response.status_code == 400
    assert response.get_json()['unsupported_files'] == ['bad.csv']
    assert imported == []


def test_single_file_upload_keeps_legacy_response_shape(
    client, two_classes, monkeypatch
):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    monkeypatch.setattr(
        'controllers.import_controller.import_data',
        lambda *args, **kwargs: {
            'success': True,
            'import_type': 'test',
            'imported_count': 7,
        },
    )
    monkeypatch.setattr(
        'controllers.import_controller.run_all_analysis',
        lambda class_id: {'summary': {'success': True}},
    )

    response = client.post('/api/import/upload', data={
        'class_id': str(first_id),
        'file': (BytesIO(b'one'), 'one.xlsx'),
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload['imported_count'] == 7
    assert 'results' not in payload
    assert 'total_files' not in payload
```

- [ ] **Step 4: Run the preflight and compatibility tests and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py -k "preflighted or unsupported_format or legacy_response_shape" -v
```

Expected: the two batch preflight tests FAIL; the legacy test documents behavior that must remain green during implementation.

- [ ] **Step 5: Implement multi-file preflight, per-file processing, and aggregation**

Refactor the current save/import block into a helper and change `upload_file()` to use `getlist`:

```python
def _import_uploaded_file(file, target_class, import_type):
    original_filename = file.filename
    filename = secure_filename(original_filename)
    if not filename or len(filename) < 5:
        ext = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else 'xls'
        filename = f'upload_{uuid4().hex}.{ext}'

    upload_folder = Path(current_app.config['UPLOAD_FOLDER'])
    upload_folder.mkdir(parents=True, exist_ok=True)
    file_path = upload_folder / f'{uuid4().hex}_{filename}'
    file.save(file_path)
    result = import_data(
        str(file_path),
        target_class.id,
        session['admin_username'],
        import_type=import_type,
        original_filename=original_filename,
        file_hash=calculate_file_hash(file_path),
    )
    result['filename'] = original_filename
    return result


def _build_batch_upload_response(results):
    imported_files = sum(bool(item.get('success')) for item in results)
    failed_files = len(results) - imported_files
    return {
        'success': failed_files == 0,
        'partial_success': imported_files > 0 and failed_files > 0,
        'message': f'共处理 {len(results)} 个文件，成功 {imported_files} 个，失败 {failed_files} 个',
        'total_files': len(results),
        'imported_files': imported_files,
        'failed_files': failed_files,
        'total_imported_rows': sum(
            (item.get('imported_count', 0) or 0)
            for item in results if item.get('success')
        ),
        'results': results,
    }
```

Within `upload_file()`:

```python
files = [file for file in request.files.getlist('file') if file.filename]
if not files:
    return jsonify({'success': False, 'message': '没有选择文件'}), 400

unsupported_files = [file.filename for file in files if not allowed_file(file.filename)]
if unsupported_files:
    return jsonify({
        'success': False,
        'message': '存在不支持的文件格式',
        'unsupported_files': unsupported_files,
    }), 400

mismatches = [
    (file.filename, _class_mismatch(file.filename, target_class))
    for file in files
]
mismatches = [(name, mismatch) for name, mismatch in mismatches if mismatch]
if mismatches and request.form.get('confirm_class_mismatch') != 'true':
    payload = dict(mismatches[0][1])
    payload['conflicting_files'] = [name for name, _ in mismatches]
    return jsonify(payload), 409

import_type = request.form.get('type', '').strip()
results = []
for file in files:
    try:
        results.append(_import_uploaded_file(file, target_class, import_type))
    except Exception as exc:
        results.append({
            'filename': file.filename,
            'success': False,
            'message': str(exc),
            'errors': [str(exc)],
            'warnings': [],
            'imported_count': 0,
        })

if len(files) == 1:
    response = results[0]
else:
    response = _build_batch_upload_response(results)

successful = any(item.get('success') for item in results)
if successful:
    try:
        response['analysis'] = run_all_analysis(target_class.id)
    except Exception as exc:
        response['analysis_warning'] = f'自动分析失败: {exc}'
return jsonify(response)
```

- [ ] **Step 6: Run backend tests and verify GREEN**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py -v
```

Expected: PASS, including all existing single-file and folder-import tests.

- [ ] **Step 7: Commit the backend behavior**

```powershell
git add controllers/import_controller.py tests/test_class_imports.py
git commit -m "feat: accept multi-file data imports"
```

---

### Task 2: General import page batch interaction

**Files:**
- Modify: `templates/import/index.html:30-53,136-230`
- Test: `tests/test_class_imports.py`

**Interfaces:**
- Consumes: the Task 1 legacy single response and aggregate multi-file response; HTTP 409 with `conflicting_files`.
- Produces: multi-select input `#file-input`, `renderUploadResult(data)`, and retry-safe `submitUpload(formData)`.

- [ ] **Step 1: Strengthen the import-page template test**

Extend `test_general_import_page_has_target_class_picker_and_no_clear_button`:

```python
assert 'id="file-input" name="file" accept=".xlsx,.xls" multiple' in html
assert "this.files.length === 1" in html
assert "'已选择 ' + this.files.length + ' 个文件'" in html
assert 'data.results.forEach(function(item)' in html
assert "payload.conflicting_files || []" in html
assert 'if (!retrying)' in html
assert ".prop('disabled', true)" in html
assert ".prop('disabled', false)" in html
```

- [ ] **Step 2: Run the template test and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py::test_general_import_page_has_target_class_picker_and_no_clear_button -v
```

Expected: FAIL because the input lacks `multiple` and the script only renders one file.

- [ ] **Step 3: Implement selection count, batch rendering, conflict confirmation, and button locking**

Change the input to:

```html
<input type="file" class="custom-file-input" id="file-input" name="file" accept=".xlsx,.xls" multiple required>
```

Use `this.files` for its label:

```javascript
$('#file-input').change(function() {
    var label = '选择文件...';
    if (this.files.length === 1) {
        label = this.files[0].name;
    } else if (this.files.length > 1) {
        label = '已选择 ' + this.files.length + ' 个文件';
    }
    $(this).next('.custom-file-label').text(label);
});
```

Add a renderer that supports both response shapes:

```javascript
function renderUploadResult(data) {
    if (!data.results) {
        var singleClass = data.success ? 'alert-success' : 'alert-danger';
        var singleMessage = data.success
            ? '导入成功，共 ' + escapeHtml(data.imported_count || 0) + ' 条。'
            : escapeHtml(data.message || '导入失败');
        return '<div class="alert ' + singleClass + '">' + singleMessage + '</div>';
    }

    var alertClass = data.success ? 'alert-success' : (data.partial_success ? 'alert-warning' : 'alert-danger');
    var html = '<div class="alert ' + alertClass + '">' +
        '<strong>' + escapeHtml(data.message) + '</strong><br>' +
        '导入数据：' + escapeHtml(data.total_imported_rows || 0) + ' 条' +
        '<ul class="mb-0 mt-2">';
    data.results.forEach(function(item) {
        var message = item.success
            ? '成功，导入 ' + escapeHtml(item.imported_count || 0) + ' 条'
            : '失败：' + escapeHtml(item.message || '未知错误');
        html += '<li>' + escapeHtml(item.filename) + '：' + message + '</li>';
    });
    return html + '</ul></div>';
}
```

In `submitUpload(formData)`, disable the submit button before `$.ajax`, declare `var retrying = false`, render `renderUploadResult(data)` in `success`, and build the confirmation text from `payload.conflicting_files || []`. When the user confirms a 409 response, set `retrying = true`, set `confirm_class_mismatch`, and call `submitUpload(formData)` again. Restore the button only for the terminal request:

```javascript
complete: function() {
    if (!retrying) {
        $('#upload-form button[type="submit"]').prop('disabled', false);
    }
}
```

The first request therefore cannot re-enable the button while its confirmed retry is still running.

- [ ] **Step 4: Run the import-page test and backend regression tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the general import page**

```powershell
git add templates/import/index.html tests/test_class_imports.py
git commit -m "feat: show batch results on import page"
```

---

### Task 3: Class detail page batch interaction and final verification

**Files:**
- Modify: `templates/class/detail.html:28-40,73-120`
- Test: `tests/test_class_imports.py`

**Interfaces:**
- Consumes: the same Task 1 response shapes and conflict payload as the general import page.
- Produces: multi-select input `#class-file-input`, batch result list in `#class-upload-result`, and disabled-state protection for the class upload button.

- [ ] **Step 1: Strengthen the class-detail template test**

Extend `test_class_detail_has_locked_upload_for_its_class`:

```python
assert 'id="class-file-input" name="file" type="file" accept=".xlsx,.xls" multiple required' in html
assert 'data.results.forEach(function (item)' in html
assert "payload.conflicting_files || []" in html
assert "$('#class-upload-form button[type=\"submit\"]')" in html
assert 'if (!retrying)' in html
assert ".prop('disabled', true)" in html
assert ".prop('disabled', false)" in html
```

- [ ] **Step 2: Run the class-detail template test and verify RED**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py::test_class_detail_has_locked_upload_for_its_class -v
```

Expected: FAIL because the class upload control and renderer are still single-file only.

- [ ] **Step 3: Implement the class-detail multi-select and batch renderer**

Change the input to:

```html
<input class="form-control-file" id="class-file-input" name="file" type="file" accept=".xlsx,.xls" multiple required>
<small class="form-text text-muted" id="class-file-count">可同时选择多个文件</small>
```

Add the selection label and batch renderer:

```javascript
$('#class-file-input').on('change', function () {
  var text = '可同时选择多个文件';
  if (this.files.length === 1) {
    text = this.files[0].name;
  } else if (this.files.length > 1) {
    text = '已选择 ' + this.files.length + ' 个文件';
  }
  $('#class-file-count').text(text);
});

function renderClassUploadResult(data) {
  if (!data.results) {
    var singleClass = data.success ? 'alert-success' : 'alert-danger';
    var singleMessage = data.success
      ? '导入成功，共 ' + escapeHtml(data.imported_count || 0) + ' 条。'
      : escapeHtml(data.message || '导入失败');
    return '<div class="alert ' + singleClass + '">' + singleMessage + '</div>';
  }

  var alertClass = data.success ? 'alert-success' : (data.partial_success ? 'alert-warning' : 'alert-danger');
  var html = '<div class="alert ' + alertClass + '">' +
    '<strong>' + escapeHtml(data.message) + '</strong><br>' +
    '导入数据：' + escapeHtml(data.total_imported_rows || 0) + ' 条' +
    '<ul class="mb-0 mt-2">';
  data.results.forEach(function (item) {
    var message = item.success
      ? '成功，导入 ' + escapeHtml(item.imported_count || 0) + ' 条'
      : '失败：' + escapeHtml(item.message || '未知错误');
    html += '<li>' + escapeHtml(item.filename) + '：' + message + '</li>';
  });
  return html + '</ul></div>';
}
```

Update `submitClassUpload` to:

```javascript
var submitButton = $('#class-upload-form button[type="submit"]');
submitButton.prop('disabled', true);
```

Render the helper output in `success`. Inside `submitClassUpload`, declare `var retrying = false`; on 409, list `payload.conflicting_files || []`, confirm once for the batch, set `retrying = true`, set `confirm_class_mismatch=true`, and retry the same `FormData`. In `complete`, restore the button only when `!retrying`, so the first request cannot unlock the form during its retry. Keep every dynamic filename and message behind `escapeHtml()`.

- [ ] **Step 4: Run focused and full verification**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_class_imports.py -v
venv\Scripts\python.exe -m pytest -v
```

Expected: both commands PASS with no new warnings or errors.

- [ ] **Step 5: Inspect the final diff for scope and encoding**

Run:

```powershell
git diff --check
git diff -- controllers/import_controller.py templates/import/index.html templates/class/detail.html tests/test_class_imports.py
git status --short
```

Expected: no whitespace errors; only the planned source/test files plus pre-existing user changes are present. Chinese UI strings remain UTF-8 and are not rewritten as mojibake.

- [ ] **Step 6: Commit the class detail interaction**

```powershell
git add templates/class/detail.html tests/test_class_imports.py
git commit -m "feat: support batch upload from class details"
```
