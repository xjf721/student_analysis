# Student Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a teacher to delete one student from the active class together with all student-scoped learning and analysis records, while allowing a later import to recreate that student number.

**Architecture:** Add one class-scoped `DELETE` endpoint to the existing student blueprint. The controller delegates to an explicit transactional delete in `StudentRepository`; the student list calls the endpoint only after a confirmation that identifies the student.

**Tech Stack:** Flask, Flask-SQLAlchemy/SQLAlchemy, pytest, jQuery, Bootstrap 5/AdminLTE

## Global Constraints

- Only a student belonging to the active class in the server-side session may be deleted.
- Delete `student_assignment_challenge`, `student_assignment_detail`, `student_behavior`, `student_practice`, `student_knowledge_mastery`, `warning_record`, and `student` in one transaction.
- Roll back the full transaction after any database error.
- Do not create an ignore list; the same student number may be imported again later.
- Do not add batch deletion, soft deletion, database migrations, or unrelated refactoring.
- Preserve all unrelated uncommitted workspace changes.

---

### Task 1: Class-scoped transactional deletion API

**Files:**
- Create: `tests/test_student_deletion.py`
- Modify: `repositories/student_repo.py`
- Modify: `controllers/student_controller.py`

**Interfaces:**
- Consumes: `get_active_class_id() -> int`, `require_active_class`, the seven existing SQLAlchemy models.
- Produces: `StudentRepository.delete(student_id: int, class_id: int) -> Optional[Dict]` and `DELETE /api/student/<int:student_id>`.

- [ ] **Step 1: Write failing integration tests for complete deletion and later recreation**

Create `tests/test_student_deletion.py` with shared login/select and seed helpers, then add this test:

```python
from models import (
    Student,
    StudentAssignmentChallenge,
    StudentAssignmentDetail,
    StudentBehavior,
    StudentKnowledgeMastery,
    StudentPractice,
    WarningRecord,
    db,
)


def login_and_select(client, class_id: int) -> None:
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def seed_student_with_all_details(app, class_id: int) -> int:
    with app.app_context():
        student = Student(student_no='TEST001', name='测试学生', class_id=class_id)
        db.session.add(student)
        db.session.flush()
        detail = StudentAssignmentDetail(
            student_id=student.id,
            assignment_name='链表实验',
        )
        db.session.add(detail)
        db.session.flush()
        db.session.add_all([
            StudentAssignmentChallenge(
                assignment_detail_id=detail.id,
                student_id=student.id,
                assignment_name='链表实验',
                challenge_name='关卡1',
            ),
            StudentBehavior(student_id=student.id, attendance_rate=100),
            StudentPractice(student_id=student.id, total_score=100),
            StudentKnowledgeMastery(
                student_id=student.id,
                knowledge_name='链表',
                mastery_rate=100,
            ),
            WarningRecord(
                student_id=student.id,
                warning_type='test',
                warning_level=1,
                warning_score=30,
                warning_reason='测试记录',
            ),
        ])
        db.session.commit()
        return student.id


def test_delete_student_removes_all_student_data_and_allows_recreation(
    app, client, two_classes
):
    class_id, _ = two_classes
    student_id = seed_student_with_all_details(app, class_id)
    with app.app_context():
        survivor = Student(student_no='REAL001', name='正式学生', class_id=class_id)
        db.session.add(survivor)
        db.session.flush()
        db.session.add(StudentBehavior(student_id=survivor.id, attendance_rate=90))
        db.session.commit()
        survivor_id = survivor.id
    login_and_select(client, class_id)

    response = client.delete(f'/api/student/{student_id}')

    assert response.status_code == 200
    assert response.get_json() == {
        'message': '已删除学生测试学生（TEST001）及其全部关联数据',
        'student': {'id': student_id, 'student_no': 'TEST001', 'name': '测试学生'},
    }
    with app.app_context():
        for model in (
            StudentAssignmentChallenge,
            StudentAssignmentDetail,
            StudentBehavior,
            StudentPractice,
            StudentKnowledgeMastery,
            WarningRecord,
        ):
            assert model.query.filter_by(student_id=student_id).count() == 0
        assert Student.query.filter_by(id=student_id).count() == 0
        assert Student.query.filter_by(id=survivor_id).count() == 1
        assert StudentBehavior.query.filter_by(student_id=survivor_id).count() == 1

        db.session.add(Student(student_no='TEST001', name='重新导入', class_id=class_id))
        db.session.commit()
        assert Student.query.filter_by(student_no='TEST001').one().name == '重新导入'
```

- [ ] **Step 2: Run the complete-deletion test and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py::test_delete_student_removes_all_student_data_and_allows_recreation -v
```

Expected: FAIL because `DELETE /api/student/<id>` currently returns HTTP 405.

- [ ] **Step 3: Write failing class-isolation and not-found tests**

Append:

```python
def test_delete_student_is_scoped_to_active_class(app, client, two_classes):
    first_id, second_id = two_classes
    student_id = seed_student_with_all_details(app, second_id)
    login_and_select(client, first_id)

    response = client.delete(f'/api/student/{student_id}')

    assert response.status_code == 404
    assert response.get_json()['error'] == 'student_not_found'
    with app.app_context():
        assert Student.query.filter_by(id=student_id).count() == 1
        assert StudentAssignmentChallenge.query.filter_by(student_id=student_id).count() == 1


def test_delete_missing_or_already_deleted_student_returns_404(app, client, two_classes):
    class_id, _ = two_classes
    student_id = seed_student_with_all_details(app, class_id)
    login_and_select(client, class_id)

    assert client.delete(f'/api/student/{student_id}').status_code == 200
    second_response = client.delete(f'/api/student/{student_id}')

    assert second_response.status_code == 404
    assert second_response.get_json() == {
        'error': 'student_not_found',
        'message': '学生不存在或不属于当前班级',
    }


def test_delete_student_rolls_back_every_record_when_commit_fails(
    app, client, two_classes, monkeypatch
):
    class_id, _ = two_classes
    student_id = seed_student_with_all_details(app, class_id)
    login_and_select(client, class_id)

    with app.app_context():
        def fail_commit() -> None:
            raise RuntimeError('forced commit failure')

        monkeypatch.setattr(db.session, 'commit', fail_commit)
        response = client.delete(f'/api/student/{student_id}')
        monkeypatch.undo()

        assert response.status_code == 500
        assert response.get_json()['error'] == 'student_delete_failed'
        assert Student.query.filter_by(id=student_id).count() == 1
        assert StudentAssignmentChallenge.query.filter_by(student_id=student_id).count() == 1
        assert StudentAssignmentDetail.query.filter_by(student_id=student_id).count() == 1
        assert StudentBehavior.query.filter_by(student_id=student_id).count() == 1
        assert StudentPractice.query.filter_by(student_id=student_id).count() == 1
        assert StudentKnowledgeMastery.query.filter_by(student_id=student_id).count() == 1
        assert WarningRecord.query.filter_by(student_id=student_id).count() == 1
```

- [ ] **Step 4: Run the new test module and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py -v
```

Expected: the first three tests FAIL with HTTP 405, and the rollback test FAILS because no delete route reaches the forced commit failure.

- [ ] **Step 5: Implement the minimal explicit repository transaction**

In `repositories/student_repo.py`, add `StudentBehavior` and `StudentPractice` to the existing `from models import (...)` list, then replace the existing unscoped `delete` method with:

```python
    @staticmethod
    def delete(student_id: int, class_id: int) -> Optional[Dict]:
        """Delete one active-class student and every student-scoped record atomically."""
        student = Student.query.filter_by(id=student_id, class_id=class_id).first()
        if not student:
            return None

        deleted_student = {
            'id': student.id,
            'student_no': student.student_no,
            'name': student.name,
        }

        try:
            StudentAssignmentChallenge.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentAssignmentDetail.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentBehavior.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentPractice.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            StudentKnowledgeMastery.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            WarningRecord.query.filter_by(student_id=student.id).delete(
                synchronize_session=False
            )
            db.session.delete(student)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return deleted_student
```

- [ ] **Step 6: Implement the minimal class-scoped controller endpoint**

In `controllers/student_controller.py`, import `current_app` from Flask and append:

```python
@student_bp.route('/api/student/<int:student_id>', methods=['DELETE'])
@require_active_class
def delete_student(student_id: int):
    """Delete one student and all associated records from the active class."""
    class_id = get_active_class_id()
    try:
        student = StudentRepository.delete(student_id, class_id)
    except Exception:
        current_app.logger.exception(
            'Failed to delete student id=%s from class id=%s',
            student_id,
            class_id,
        )
        return jsonify({
            'error': 'student_delete_failed',
            'message': '删除学生失败，请稍后重试',
        }), 500

    if not student:
        return jsonify({
            'error': 'student_not_found',
            'message': '学生不存在或不属于当前班级',
        }), 404

    return jsonify({
        'message': f'已删除学生{student["name"]}（{student["student_no"]}）及其全部关联数据',
        'student': student,
    })
```

- [ ] **Step 7: Run the deletion API tests and verify GREEN**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Run nearby class-isolation tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_class_isolation.py tests/test_classes.py -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit the API and repository change**

```powershell
git add -- tests/test_student_deletion.py repositories/student_repo.py controllers/student_controller.py
git commit -m "feat: delete students with associated data"
```

---

### Task 2: Student-list deletion control

**Files:**
- Modify: `tests/test_student_deletion.py`
- Modify: `templates/student/list.html`

**Interfaces:**
- Consumes: `DELETE /api/student/<student_id>` and its `message` response.
- Produces: one `.delete-student` control per rendered row and a delegated click handler with confirmation, success reload, and error feedback.

- [ ] **Step 1: Write a failing rendered-page interaction contract test**

Append to `tests/test_student_deletion.py`:

```python
def test_student_list_includes_confirmed_delete_interaction(client, two_classes):
    class_id, _ = two_classes
    login_and_select(client, class_id)

    page = client.get('/students').get_data(as_text=True)

    assert 'class="btn btn-sm btn-danger delete-student ml-1"' in page
    assert "$('#student-table').on('click', '.delete-student'" in page
    assert "student.name + '（学号：' + student.student_no + '）'" in page
    assert '全部学习与分析数据将被删除' in page
    assert "type: 'DELETE'" in page
    assert 'loadStudents();' in page
    assert "xhr.responseJSON && xhr.responseJSON.message" in page
```

- [ ] **Step 2: Run the page test and verify RED**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py::test_student_list_includes_confirmed_delete_interaction -v
```

Expected: FAIL because the list template does not yet contain `.delete-student`.

- [ ] **Step 3: Add the minimal list control and interaction**

In `templates/student/list.html`:

1. Declare `var studentsById = {};` inside the ready callback before `loadStudents()`.
2. At the start of the successful `$.get` callback set `studentsById = {};`.
3. Inside `data.forEach`, set `studentsById[student.id] = student;`.
4. Extend the operation cell with:

```javascript
'<button type="button" class="btn btn-sm btn-danger delete-student ml-1" data-student-id="' + student.id + '">删除</button>' +
```

5. Add this delegated handler after `loadStudents`:

```javascript
    $('#student-table').on('click', '.delete-student', function() {
        var student = studentsById[$(this).data('student-id')];
        if (!student) {
            alert('未找到要删除的学生，请刷新页面后重试。');
            return;
        }

        var confirmed = confirm(
            '确认删除学生' + student.name + '（学号：' + student.student_no + '）吗？\n' +
            '该学生的全部学习与分析数据将被删除，此操作无法撤销。'
        );
        if (!confirmed) {
            return;
        }

        $.ajax({
            url: '/api/student/' + student.id,
            type: 'DELETE',
            success: function(response) {
                alert(response.message);
                loadStudents();
            },
            error: function(xhr) {
                var message = xhr.responseJSON && xhr.responseJSON.message
                    ? xhr.responseJSON.message
                    : '删除学生失败，请稍后重试。';
                alert(message);
            }
        });
    });
```

- [ ] **Step 4: Run the page contract test and verify GREEN**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py::test_student_list_includes_confirmed_delete_interaction -v
```

Expected: 1 passed.

- [ ] **Step 5: Run the complete focused test module**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_student_deletion.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit the list interaction**

```powershell
git add -- tests/test_student_deletion.py templates/student/list.html
git commit -m "feat: add student deletion control"
```

---

### Task 3: Full regression verification

**Files:**
- Verify only; no planned file changes.

**Interfaces:**
- Consumes: the completed repository, endpoint, and student-list interaction.
- Produces: fresh evidence that the full suite passes and the diff contains only intended changes.

- [ ] **Step 1: Run the full automated test suite**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Expected: exit code 0 with zero failed tests.

- [ ] **Step 2: Check whitespace and inspect the scoped diff**

Run:

```powershell
git diff --check
git status --short
git diff -- controllers/student_controller.py repositories/student_repo.py templates/student/list.html tests/test_student_deletion.py
```

Expected: `git diff --check` exits 0; the scoped diff contains only the student-deletion implementation, while pre-existing unrelated modified files remain untouched.

- [ ] **Step 3: Verify requirement coverage**

Confirm from test output and diff:

- The endpoint is active-class scoped and returns 404 for cross-class access.
- All six dependent tables plus the student row are deleted atomically.
- Another student remains unaffected.
- The same student number can be inserted after deletion.
- The list requires a named confirmation and handles success/error responses.
- No importer, schema, bulk-delete, or soft-delete behavior was added.
