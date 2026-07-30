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
    """Authenticate and select the class used by student APIs."""
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def seed_student_with_all_details(app, class_id: int) -> int:
    """Create one student with every student-scoped dependent record."""
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


def test_student_list_includes_confirmed_delete_interaction(client, two_classes):
    class_id, _ = two_classes
    login_and_select(client, class_id)

    page = client.get('/students').get_data(as_text=True)

    assert 'class="btn btn-sm btn-danger delete-student ml-1"' in page
    assert "$('#student-table').on('click', '.delete-student'" in page
    assert "'确认删除学生' + student.name" in page
    assert "'（学号：' + student.student_no + '）吗？" in page
    assert '全部学习与分析数据将被删除' in page
    assert "type: 'DELETE'" in page
    assert 'loadStudents();' in page
    assert "xhr.responseJSON && xhr.responseJSON.message" in page
