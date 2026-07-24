# 班级管理、数据隔离与登录模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 Flask 教学分析平台增加单管理员认证、全局当前班级、全链路班级数据隔离、班级内导入和班级对比能力。

**Architecture:** 使用 Flask Session 保存认证状态和 `active_class_id`，通过统一请求守卫加载当前班级；控制器必须把班级 ID 显式传入 Repository 和 Analyzer，普通查询不保留全量默认值。上传以用户选择的班级为唯一数据归属，文件名只做冲突校验，只有班级对比服务可以显式聚合多个班级。

**Tech Stack:** Python 3、Flask 3、Flask-SQLAlchemy、MySQL 8、Flask-WTF、Flask-Limiter、pytest、Bootstrap/AdminLTE、jQuery、ECharts。

## Global Constraints

- 用户名从 `ADMIN_USERNAME` 环境变量读取，密码哈希从 `ADMIN_PASSWORD_HASH` 环境变量读取；代码中不得提供可直接登录的默认密码。
- 普通业务页面任一时刻只展示一个明确班级的数据，不提供“全部班级”兜底。
- 上传、导入、分析和展示必须使用同一个显式目标班级。
- 只有独立班级对比接口可以读取多个班级，且不得返回混合学生明细。
- 现有数据库业务数据不迁移；数据库重建只能通过带显式确认参数的命令执行，应用启动不得自动清空数据。
- 保留工作区中现有的作业明细、知识点汇总等未提交改动；每次提交只暂存本任务列出的文件。

---

## 文件结构与职责

### 新建文件

- `extensions.py`：集中定义 CSRF 和限流扩展，避免循环导入。
- `services/auth_service.py`：管理员凭据校验。
- `services/class_context.py`：认证守卫、当前班级加载、模板上下文和 API/页面错误分流。
- `repositories/class_repo.py`：班级 CRUD、状态切换和概览统计。
- `controllers/auth_controller.py`：登录和退出。
- `controllers/class_controller.py`：班级管理、班级选择、详情和重新分析入口。
- `services/class_comparison.py`：班级指标对比的唯一跨班聚合入口。
- `templates/auth/login.html`：登录页。
- `templates/class/index.html`：班级管理与选择页。
- `templates/class/detail.html`：班级详情和班级内上传入口。
- `templates/class/compare.html`：班级对比页。
- `tests/conftest.py`：SQLite 测试应用、登录客户端和两班数据夹具。
- `tests/test_auth.py`：认证、会话、CSRF 和限流测试。
- `tests/test_classes.py`：班级 CRUD、选择、归档和删除保护测试。
- `tests/test_class_isolation.py`：控制器、Repository 和学生详情隔离测试。
- `tests/test_class_imports.py`：班级归属、文件冲突、同名文件和定向分析测试。
- `tests/test_class_comparison.py`：班级对比口径测试。
- `tests/test_database_reset.py`：受控重建参数测试。

### 重点修改文件

- `app.py`、`config.py`、`requirements.txt`：扩展初始化、蓝图注册和安全配置。
- `models/class_model.py`、`models/import_record.py`、`models/student.py`、`models/knowledge_point_summary.py`：班级状态、导入归属和非空外键。
- `controllers/dashboard_controller.py`、`student_controller.py`、`knowledge_controller.py`、`warning_controller.py`、`import_controller.py`：使用统一当前班级。
- `repositories/student_repo.py`、`behavior_repo.py`、`knowledge_repo.py`、`warning_repo.py`：所有普通聚合和列表查询要求 `class_id`。
- `services/analysis/*.py`：所有批量分析要求 `class_id`。
- `services/importers/base_importer.py`、`rainclass_importer.py`、`educoder_importer.py`：显式目标班级和单文件事务。
- `templates/base.html`、各业务模板：当前班级标签、切换器、CSRF 请求头和新增导航。
- `init_database.py`、`README.md`：受控重建和部署说明。

---

### Task 1: 建立测试基线、安全扩展与新数据结构

**Files:**
- Create: `extensions.py`
- Create: `tests/conftest.py`
- Create: `tests/test_schema.py`
- Modify: `requirements.txt`
- Modify: `config.py`
- Modify: `app.py`
- Modify: `models/base.py`
- Modify: `models/class_model.py`
- Modify: `models/import_record.py`
- Modify: `models/student.py`
- Modify: `models/knowledge_point_summary.py`

**Interfaces:**
- Produces: `csrf: CSRFProtect`、`limiter: Limiter`。
- Produces: `ClassInfo.status`、`ClassInfo.notes`、`ImportRecord.class_id/file_hash/uploaded_by`。
- Produces: pytest fixture `app`、`client`、`two_classes`。

- [ ] **Step 1: 添加测试与安全依赖**

在 `requirements.txt` 追加固定版本：

```text
Flask-WTF==1.2.2
Flask-Limiter==3.12
pytest==8.3.5
```

- [ ] **Step 2: 写数据结构失败测试**

创建 `tests/test_schema.py`：

```python
from sqlalchemy import inspect


def test_class_and_import_schema(app):
    with app.app_context():
        inspector = inspect(app.extensions['sqlalchemy'].engine)
        class_columns = {item['name'] for item in inspector.get_columns('class_info')}
        import_columns = {item['name'] for item in inspector.get_columns('import_record')}
        student_columns = {item['name']: item for item in inspector.get_columns('student')}

    assert {'status', 'notes'} <= class_columns
    assert {'class_id', 'file_hash', 'uploaded_by'} <= import_columns
    assert student_columns['class_id']['nullable'] is False
```

- [ ] **Step 3: 创建可复用测试应用夹具**

创建 `tests/conftest.py`，测试库固定使用临时 SQLite 文件，避免触碰本地 MySQL：

```python
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
```

- [ ] **Step 4: 运行测试确认失败**

Run: `pytest tests/test_schema.py -q`

Expected: FAIL，提示缺少 `status`、`notes`、`class_id`、`file_hash` 或 `uploaded_by`。

- [ ] **Step 5: 实现扩展对象和配置覆盖接口**

创建 `extensions.py`：

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

在 `config.py` 的 `Config` 中加入：

```python
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
WTF_CSRF_TIME_LIMIT = 3600
RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
```

将 `create_app` 签名改为：

```python
def create_app(config_name: str = 'dev', overrides: dict = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if overrides:
        app.config.update(overrides)
```

在加载配置后初始化：

```python
from extensions import csrf, limiter

csrf.init_app(app)
limiter.init_app(app)
```

修改 `models/base.py::init_db`，只有 MySQL URI 才调用 `ensure_database_exists`：

```python
def init_db(app) -> None:
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('mysql'):
        ensure_database_exists(app)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
```

- [ ] **Step 6: 实现新字段**

在 `ClassInfo` 中加入：

```python
status = Column(String(20), nullable=False, default='active', index=True, comment='active/archived')
notes = Column(String(500), nullable=True, comment='班级备注')
```

在 `ImportRecord` 中加入：

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class_id = Column(Integer, ForeignKey('class_info.id'), nullable=False, index=True)
file_hash = Column(String(64), nullable=False, index=True)
uploaded_by = Column(String(100), nullable=False)
class_info = relationship('ClassInfo')
```

同时将 `Student.class_id` 和 `KnowledgePointSummary.class_id` 改为 `nullable=False`。更新 `to_dict()`，返回班级状态、备注、导入班级 ID、班级名称、摘要和上传人。`ImportRecord.is_imported` 改为：

```python
@classmethod
def is_imported(cls, class_id: int, file_hash: str) -> bool:
    return cls.query.filter_by(
        class_id=class_id,
        file_hash=file_hash,
        import_status='成功',
    ).first() is not None

@classmethod
def get_recent_records(cls, class_id: int, limit: int = 20):
    return cls.query.filter_by(class_id=class_id).order_by(cls.created_at.desc()).limit(limit).all()
```

- [ ] **Step 7: 运行结构测试**

Run: `pytest tests/test_schema.py -q`

Expected: `1 passed`。

- [ ] **Step 8: 提交**

```bash
git add requirements.txt config.py app.py extensions.py models/base.py models/class_model.py models/import_record.py models/student.py models/knowledge_point_summary.py tests/conftest.py tests/test_schema.py
git commit -m "feat: add class-aware schema and test foundation"
```

---

### Task 2: 实现单管理员登录与请求保护

**Files:**
- Create: `services/auth_service.py`
- Create: `services/class_context.py`
- Create: `controllers/auth_controller.py`
- Create: `templates/auth/login.html`
- Create: `tests/test_auth.py`
- Modify: `controllers/__init__.py`
- Modify: `app.py`
- Modify: `templates/base.html`

**Interfaces:**
- Produces: `authenticate(username: str, password: str) -> bool`。
- Produces: `login_required` 请求守卫和 `session['authenticated']`。
- Produces: routes `GET|POST /login`、`POST /logout`。

- [ ] **Step 1: 写认证失败测试**

创建 `tests/test_auth.py`：

```python
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
        'username': 'admin', 'password': 'correct-password'
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
        assert limited_client.post('/login', data={'username': 'admin', 'password': 'wrong'}).status_code == 401
    assert limited_client.post('/login', data={'username': 'admin', 'password': 'wrong'}).status_code == 429
```

在该测试文件顶部导入 `generate_password_hash`：

```python
from werkzeug.security import generate_password_hash
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_auth.py -q`

Expected: FAIL，`/login` 不存在且业务页面仍可匿名访问。

- [ ] **Step 3: 实现凭据校验**

创建 `services/auth_service.py`：

```python
import hmac

from flask import current_app
from werkzeug.security import check_password_hash


def credentials_configured() -> bool:
    return bool(current_app.config.get('ADMIN_USERNAME') and current_app.config.get('ADMIN_PASSWORD_HASH'))


def authenticate(username: str, password: str) -> bool:
    if not credentials_configured():
        return False
    expected_username = current_app.config['ADMIN_USERNAME']
    username_ok = hmac.compare_digest(username or '', expected_username)
    password_ok = check_password_hash(current_app.config['ADMIN_PASSWORD_HASH'], password or '')
    return username_ok and password_ok
```

- [ ] **Step 4: 实现登录控制器**

创建 `controllers/auth_controller.py`：

```python
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from extensions import limiter
from services.auth_service import authenticate, credentials_configured

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per 15 minutes', methods=['POST'])
def login():
    if not credentials_configured():
        return render_template('auth/login.html', config_error=True), 503
    if request.method == 'GET':
        return render_template('auth/login.html', config_error=False)
    if not authenticate(request.form.get('username', ''), request.form.get('password', '')):
        return render_template('auth/login.html', error='用户名或密码错误', config_error=False), 401
    session.clear()
    session['authenticated'] = True
    session['admin_username'] = current_app.config['ADMIN_USERNAME']
    return redirect(url_for('classes.index'))


@auth_bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
```

- [ ] **Step 5: 实现全局认证守卫**

在 `services/class_context.py` 先实现认证部分：

```python
from flask import jsonify, redirect, request, session, url_for

PUBLIC_ENDPOINTS = {'auth.login', 'static'}


def install_request_guards(app):
    @app.before_request
    def require_authentication():
        if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if session.get('authenticated'):
            return None
        if request.path.startswith('/api/'):
            return jsonify({'error': 'authentication_required'}), 401
        return redirect(url_for('auth.login', next=request.full_path))
```

在 `controllers/__init__.py` 导出 `auth_bp`，在 `app.py` 注册该蓝图并调用 `install_request_guards(app)`。

- [ ] **Step 6: 创建登录模板和退出按钮**

`templates/auth/login.html` 使用独立简洁布局，表单必须包含：

```html
<form method="post" action="{{ url_for('auth.login') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input name="username" autocomplete="username" required>
  <input name="password" type="password" autocomplete="current-password" required>
  <button type="submit">登录</button>
</form>
```

在 `templates/base.html` 顶部加入带 CSRF 的退出表单：

```html
<form method="post" action="{{ url_for('auth.logout') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <button class="btn btn-link nav-link" type="submit">退出</button>
</form>
```

- [ ] **Step 7: 运行认证测试**

Run: `pytest tests/test_auth.py -q`

Expected: `6 passed`。

- [ ] **Step 8: 提交**

```bash
git add services/auth_service.py services/class_context.py controllers/auth_controller.py controllers/__init__.py app.py templates/auth/login.html templates/base.html tests/test_auth.py
git commit -m "feat: require administrator login"
```

---

### Task 3: 实现班级管理与全局当前班级上下文

**Files:**
- Create: `repositories/class_repo.py`
- Create: `controllers/class_controller.py`
- Create: `templates/class/index.html`
- Create: `templates/class/detail.html`
- Create: `tests/test_classes.py`
- Modify: `repositories/__init__.py`
- Modify: `controllers/__init__.py`
- Modify: `services/class_context.py`
- Modify: `app.py`
- Modify: `templates/base.html`

**Interfaces:**
- Produces: `ClassRepository` CRUD 与 `get_overview(class_id)`。
- Produces: `get_active_class_id() -> int`、`require_active_class`。
- Produces: `/classes`、`/classes/<id>`、`/api/classes/*`、`POST /api/classes/<id>/select`。

- [ ] **Step 1: 写班级生命周期失败测试**

创建 `tests/test_classes.py`：

```python
from models import ClassInfo, Student, db


def login(client):
    return client.post('/login', data={'username': 'admin', 'password': 'correct-password'})


def test_create_select_archive_restore_and_delete_empty(app, client):
    login(client)
    created = client.post('/api/classes', json={
        'class_name': '青年3班', 'term': '2026春', 'teacher_name': '张老师', 'notes': '测试班'
    })
    assert created.status_code == 201
    class_id = created.get_json()['id']

    selected = client.post(f'/api/classes/{class_id}/select')
    assert selected.status_code == 200
    with client.session_transaction() as session:
        assert session['active_class_id'] == class_id

    assert client.post(f'/api/classes/{class_id}/archive').status_code == 200
    with client.session_transaction() as session:
        assert 'active_class_id' not in session

    assert client.post(f'/api/classes/{class_id}/restore').status_code == 200
    assert client.delete(f'/api/classes/{class_id}').status_code == 200


def test_class_with_students_cannot_be_deleted(app, client, two_classes):
    login(client)
    first_id, _ = two_classes
    with app.app_context():
        db.session.add(Student(student_no='20260001', name='甲', class_id=first_id))
        db.session.commit()
    response = client.delete(f'/api/classes/{first_id}')
    assert response.status_code == 409
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_classes.py -q`

Expected: FAIL，班级 API 不存在。

- [ ] **Step 3: 实现班级 Repository**

创建 `repositories/class_repo.py`，公开以下完整接口：

```python
from sqlalchemy import func

from models import ClassInfo, ImportRecord, KnowledgePointSummary, Student, db


class ClassRepository:
    @staticmethod
    def get_by_id(class_id: int):
        return db.session.get(ClassInfo, class_id)

    @staticmethod
    def get_active():
        return ClassInfo.query.filter_by(status='active').order_by(ClassInfo.term.desc(), ClassInfo.class_name).all()

    @staticmethod
    def create(data: dict):
        item = ClassInfo(
            class_name=data['class_name'].strip(),
            teacher_name=(data.get('teacher_name') or '').strip() or None,
            term=(data.get('term') or '').strip() or None,
            notes=(data.get('notes') or '').strip() or None,
            status='active',
        )
        db.session.add(item)
        db.session.commit()
        return item

    @staticmethod
    def has_data(class_id: int) -> bool:
        checks = (
            Student.query.filter_by(class_id=class_id).first(),
            ImportRecord.query.filter_by(class_id=class_id).first(),
            KnowledgePointSummary.query.filter_by(class_id=class_id).first(),
        )
        return any(checks)

    @staticmethod
    def delete_empty(item: ClassInfo) -> bool:
        if ClassRepository.has_data(item.id):
            return False
        db.session.delete(item)
        db.session.commit()
        return True

    @staticmethod
    def get_overview(class_id: int) -> dict:
        return {
            'student_count': Student.query.filter_by(class_id=class_id).count(),
            'import_count': ImportRecord.query.filter_by(class_id=class_id).count(),
            'latest_import_at': db.session.query(func.max(ImportRecord.created_at)).filter(
                ImportRecord.class_id == class_id
            ).scalar(),
        }
```

控制器中的编辑、归档和恢复直接更新允许字段并统一 `db.session.commit()`；班级名为空返回 400，不存在返回 404，有数据删除返回 409。

- [ ] **Step 4: 加载当前班级并注入模板**

扩展 `services/class_context.py`：

```python
from functools import wraps
from flask import g, jsonify, redirect, request, session, url_for
from models import ClassInfo


def get_active_class_id() -> int:
    return g.active_class.id


def require_active_class(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        class_id = session.get('active_class_id')
        active = ClassInfo.query.filter_by(id=class_id, status='active').first() if class_id else None
        if active is None:
            session.pop('active_class_id', None)
            if request.path.startswith('/api/'):
                return jsonify({'error': 'active_class_required'}), 409
            return redirect(url_for('classes.index'))
        g.active_class = active
        return view(*args, **kwargs)
    return wrapped


def install_template_context(app):
    @app.context_processor
    def class_navigation_context():
        if not session.get('authenticated'):
            return {}
        class_id = session.get('active_class_id')
        return {
            'active_class': ClassInfo.query.filter_by(id=class_id, status='active').first(),
            'active_classes': ClassInfo.query.filter_by(status='active').order_by(ClassInfo.class_name).all(),
        }
```

- [ ] **Step 5: 实现班级控制器和页面**

`controllers/class_controller.py` 使用蓝图名 `classes`，实现：

```text
GET    /classes
GET    /classes/<int:class_id>
GET    /api/classes
POST   /api/classes
PATCH  /api/classes/<int:class_id>
POST   /api/classes/<int:class_id>/select
POST   /api/classes/<int:class_id>/archive
POST   /api/classes/<int:class_id>/restore
DELETE /api/classes/<int:class_id>
```

选择班级的核心逻辑必须是：

```python
item = ClassInfo.query.filter_by(id=class_id, status='active').first_or_404()
session['active_class_id'] = item.id
return jsonify({'success': True, 'redirect': url_for('dashboard.index')})
```

`templates/class/index.html` 展示班级卡片、状态、人数、导入数和操作按钮；`templates/class/detail.html` 展示班级概览、最近导入和上传入口。所有写请求使用 JSON 或表单，并携带 CSRF Token。

- [ ] **Step 6: 加入顶部切换器和导航**

在 `templates/base.html` 增加班级管理、班级对比导航；顶部选择器提交到选择 API。全局 AJAX CSRF 配置为：

```html
<meta name="csrf-token" content="{{ csrf_token() }}">
<script>
$.ajaxSetup({
  beforeSend: function(xhr, settings) {
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type)) {
      xhr.setRequestHeader('X-CSRFToken', document.querySelector('meta[name="csrf-token"]').content);
    }
  }
});
</script>
```

- [ ] **Step 7: 运行班级测试**

Run: `pytest tests/test_classes.py -q`

Expected: `2 passed`。

- [ ] **Step 8: 提交**

```bash
git add repositories/class_repo.py repositories/__init__.py controllers/class_controller.py controllers/__init__.py services/class_context.py app.py templates/class/index.html templates/class/detail.html templates/base.html tests/test_classes.py
git commit -m "feat: add class management and active class context"
```

---

### Task 4: 强制所有普通查询和分析使用当前班级

**Files:**
- Create: `tests/test_class_isolation.py`
- Modify: `repositories/student_repo.py`
- Modify: `repositories/behavior_repo.py`
- Modify: `repositories/knowledge_repo.py`
- Modify: `repositories/warning_repo.py`
- Modify: `services/analysis/behavior_analyzer.py`
- Modify: `services/analysis/knowledge_analyzer.py`
- Modify: `services/analysis/practice_analyzer.py`
- Modify: `services/analysis/warning_engine.py`
- Modify: `controllers/dashboard_controller.py`
- Modify: `controllers/student_controller.py`
- Modify: `controllers/knowledge_controller.py`
- Modify: `controllers/warning_controller.py`

**Interfaces:**
- Consumes: `get_active_class_id()`、`require_active_class`。
- Produces: 所有普通列表、聚合、详情和批量分析均要求 `class_id: int`。

- [ ] **Step 1: 写跨班隔离失败测试**

创建 `tests/test_class_isolation.py`：

```python
from models import Student, StudentBehavior, db


def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def test_lists_and_details_are_scoped(app, client, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        first = Student(student_no='20260001', name='一班学生', class_id=first_id)
        second = Student(student_no='20260002', name='二班学生', class_id=second_id)
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add_all([
            StudentBehavior(student_id=first.id, attendance_rate=90),
            StudentBehavior(student_id=second.id, attendance_rate=20),
        ])
        db.session.commit()
        second_student_id = second.id

    login_and_select(client, first_id)
    rows = client.get('/api/students').get_json()
    assert [row['name'] for row in rows] == ['一班学生']
    assert client.get(f'/api/student/{second_student_id}').status_code == 404
    stats = client.get('/api/stats').get_json()
    assert stats['total_students'] == 1
    assert stats['avg_attendance_rate'] == 90


def test_query_class_id_cannot_override_session(client, two_classes):
    first_id, second_id = two_classes
    login_and_select(client, first_id)
    response = client.get(f'/api/students?class_id={second_id}')
    assert response.status_code == 200
    assert all(item['class_id'] == first_id for item in response.get_json())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_class_isolation.py -q`

Expected: FAIL，当前控制器仍接受查询参数或执行全量查询。

- [ ] **Step 3: 收紧 Repository 签名**

将以下接口改为强制 `class_id: int`，并在查询中加入 `Student.class_id == class_id` 或模型自身 `class_id == class_id`：

```python
StudentRepository.get_by_id(student_id: int, class_id: int)
StudentRepository.get_all(class_id: int)
StudentRepository.get_with_details(student_id: int, class_id: int)
StudentRepository.get_full_overview(student_id: int, class_id: int)
StudentRepository.get_count(class_id: int)
StudentRepository.search(keyword: str, class_id: int, limit: int = 20)

BehaviorRepository.get_all(class_id: int)
BehaviorRepository.get_statistics(class_id: int)
BehaviorRepository.get_low_attendance(class_id: int, threshold: float = 60.0, limit: int = 20)
BehaviorRepository.get_top_performers(class_id: int, limit: int = 10)

KnowledgeRepository.get_all_knowledge_names(class_id: int)
KnowledgeRepository.get_knowledge_statistics(class_id: int)
KnowledgeRepository.get_point_summary_statistics(class_id: int, limit: int = None)
KnowledgeRepository.get_weak_knowledge_points(class_id: int, threshold: float = 40.0)
KnowledgeRepository.get_students_by_knowledge(class_id: int, knowledge_name: str, min_rate=None, max_rate=None, limit: int = 50)
KnowledgeRepository.get_heatmap_data(class_id: int, knowledge_limit: int = 20, student_limit: int = 50)

WarningRepository.get_high_risk_students(class_id: int, min_score: float = 60.0, limit: int = 50)
WarningRepository.get_statistics(class_id: int)
WarningRepository.get_type_distribution(class_id: int)
WarningRepository.get_by_level(class_id: int, level: int, limit: int = 50)
```

详情查询必须采用组合条件：

```python
return Student.query.filter_by(id=student_id, class_id=class_id).first()
```

- [ ] **Step 4: 收紧 Analyzer 构造函数**

四个分析器统一改为：

```python
def __init__(self, class_id: int):
    if not class_id:
        raise ValueError('class_id is required')
    self.class_id = class_id
```

删除“`class_id is None` 则全年级”的分支。分析产生、更新或删除记录时，先通过 `Student.class_id == self.class_id` 得到学生集合，禁止影响其他班级。

- [ ] **Step 5: 控制器统一读取当前班级**

所有业务页面和 API 添加 `@require_active_class`，并在函数首行使用：

```python
class_id = get_active_class_id()
```

控制器不再读取请求中的 `class_id`。例如学生列表改为：

```python
@student_bp.get('/api/students')
@require_active_class
def get_students():
    class_id = get_active_class_id()
    keyword = request.args.get('keyword', '').strip()
    students = (
        StudentRepository.search(keyword, class_id)
        if keyword else StudentRepository.get_all(class_id)
    )
    return jsonify([student.to_dict() for student in students])
```

Dashboard 的所有 Repository/Analyzer 调用传入同一个 `class_id`。`/api/debug/stats` 要么删除，要么按当前班级过滤；计划采用删除该生产诊断接口。

- [ ] **Step 6: 运行隔离和旧功能测试**

Run: `pytest tests/test_class_isolation.py tests/test_auth.py tests/test_classes.py -q`

Expected: 全部 PASS。

- [ ] **Step 7: 静态扫描遗漏的无班级调用**

Run: `rg -n "get_statistics\(\)|get_all\(\)|get_count\(\)|BehaviorAnalyzer\(\)|KnowledgeAnalyzer\(\)|PracticeAnalyzer\(\)|WarningEngine\(\)" controllers repositories services`

Expected: 没有普通业务调用以空参数执行班级相关查询或分析。

- [ ] **Step 8: 提交**

```bash
git add repositories/student_repo.py repositories/behavior_repo.py repositories/knowledge_repo.py repositories/warning_repo.py services/analysis/behavior_analyzer.py services/analysis/knowledge_analyzer.py services/analysis/practice_analyzer.py services/analysis/warning_engine.py controllers/dashboard_controller.py controllers/student_controller.py controllers/knowledge_controller.py controllers/warning_controller.py tests/test_class_isolation.py
git commit -m "feat: enforce class isolation across analytics"
```

---

### Task 5: 将上传、导入记录和重新分析绑定到目标班级

**Files:**
- Create: `tests/test_class_imports.py`
- Modify: `services/importers/base_importer.py`
- Modify: `services/importers/rainclass_importer.py`
- Modify: `services/importers/educoder_importer.py`
- Modify: `controllers/import_controller.py`
- Modify: `templates/import/index.html`
- Modify: `templates/class/detail.html`

**Interfaces:**
- Produces: `calculate_file_hash(path: Path) -> str`。
- Produces: `BaseImporter(file_path, class_id, uploaded_by, display_filename=None, file_hash=None)`。
- Produces: `run_all_analysis(class_id: int) -> dict`。
- Produces: 文件班级冲突响应 `409`，错误码 `class_name_mismatch`。

- [ ] **Step 1: 写导入归属失败测试**

创建 `tests/test_class_imports.py`，使用 monkeypatch 替代真实 Excel 解析：

```python
from pathlib import Path


def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def test_filename_class_mismatch_requires_confirmation(client, two_classes, tmp_path, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    file_path = tmp_path / '2026春-青年2班-雨课堂-成绩单.xlsx'
    file_path.write_bytes(b'fake excel')

    with file_path.open('rb') as stream:
        response = client.post('/api/import/upload', data={
            'class_id': str(first_id),
            'file': (stream, file_path.name),
        })

    assert response.status_code == 409
    payload = response.get_json()
    assert payload['error'] == 'class_name_mismatch'
    assert payload['selected_class'] == '青年1班'
    assert payload['detected_class'] == '青年2班'


def test_analysis_receives_target_class(client, two_classes, monkeypatch):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    observed = []
    monkeypatch.setattr('controllers.import_controller.run_all_analysis', lambda class_id: observed.append(class_id) or {'summary': {'success': True}})
    response = client.post('/api/import/analyze')
    assert response.status_code == 200
    assert observed == [first_id]


def test_same_filename_is_independent_between_classes(app, two_classes):
    from models import ImportRecord, db
    first_id, second_id = two_classes
    with app.app_context():
        db.session.add_all([
            ImportRecord(class_id=first_id, filename='成绩单.xlsx', file_hash='a' * 64,
                         uploaded_by='admin', import_type='雨课堂', import_status='成功'),
            ImportRecord(class_id=second_id, filename='成绩单.xlsx', file_hash='a' * 64,
                         uploaded_by='admin', import_type='雨课堂', import_status='成功'),
        ])
        db.session.commit()
        assert ImportRecord.query.filter_by(filename='成绩单.xlsx').count() == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_class_imports.py -q`

Expected: FAIL，上传接口未要求班级，分析仍无参数。

- [ ] **Step 3: 实现文件摘要和显式目标班级**

在 `base_importer.py` 加入：

```python
import hashlib


def calculate_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
```

构造函数改为：

```python
def __init__(self, file_path: str, class_id: int, uploaded_by: str,
             display_filename: str = None, file_hash: str = None):
    self.file_path = Path(file_path)
    self.display_filename = display_filename or self.file_path.name
    self.filename = self.display_filename
    self.class_id = class_id
    self.uploaded_by = uploaded_by
    self.file_hash = file_hash or calculate_file_hash(self.file_path)
    self.detected_class_info = extract_class_info_from_filename(self.display_filename)
```

用下面方法替代 `_get_or_create_class()`：

```python
def _get_target_class_id(self) -> int:
    from models import ClassInfo
    item = ClassInfo.query.filter_by(id=self.class_id, status='active').first()
    if item is None:
        raise ValueError('目标班级不存在或已归档')
    return item.id
```

所有导入器把 `_get_or_create_class()` 调用替换为 `_get_target_class_id()`，禁止自动创建班级。

- [ ] **Step 4: 按班级和摘要记录导入**

BaseImporter 校验使用：

```python
if ImportRecord.is_imported(self.class_id, self.file_hash):
    self.warnings.append('该文件已在当前班级导入过，将覆盖对应数据')
```

保存前只删除同班同摘要的旧记录：

```python
ImportRecord.query.filter_by(class_id=self.class_id, file_hash=self.file_hash).delete(
    synchronize_session=False
)
self.import_record = ImportRecord(
    class_id=self.class_id,
    filename=self.filename,
    file_hash=self.file_hash,
    uploaded_by=self.uploaded_by,
    import_type=self.import_type,
    import_status='进行中',
)
```

将各导入器内部的 `db.session.commit()` 改为 `db.session.flush()`，让一个文件的解析数据和导入记录处于同一事务。失败时 `db.session.rollback()`，再单独写入一条状态为“失败”的 `ImportRecord` 并提交。

- [ ] **Step 5: 实现上传冲突握手**

`upload_file()` 必须：

1. 从表单读取 `class_id`，并验证其等于当前班级或用户明确改选的活动班级。
2. 在保存和导入前调用 `extract_class_info_from_filename(original_filename)`。
3. 若检测班级与目标班级名称不同且 `confirm_class_mismatch != 'true'`，返回：

```python
return jsonify({
    'error': 'class_name_mismatch',
    'message': '文件名中的班级与目标班级不一致',
    'selected_class': target_class.class_name,
    'detected_class': detected['class_name'],
}), 409
```

4. 构造导入器时传入 `class_id`、`session['admin_username']` 和文件摘要。
5. 成功后调用 `run_all_analysis(class_id)`。

批量文件夹导入也必须接收单一目标 `class_id`；发现任一文件冲突时把该文件标记为待确认，不静默导入。

- [ ] **Step 6: 定向导入记录和分析**

`get_import_records()` 改为 `ImportRecord.get_recent_records(get_active_class_id(), limit)`。`run_all_analysis` 改为：

```python
def run_all_analysis(class_id: int) -> dict:
    analyzers = {
        'behavior': BehaviorAnalyzer(class_id),
        'practice': PracticeAnalyzer(class_id),
        'knowledge': KnowledgeAnalyzer(class_id),
        'warning': WarningEngine(class_id),
    }
    results = {}
    for name, analyzer in analyzers.items():
        try:
            results[name] = analyzer.analyze_all()
        except Exception as exc:
            results[name] = {'success': False, 'message': str(exc)}
    analyzed_count = sum(
        item.get('analyzed_count', 0)
        for item in results.values()
        if item.get('success', True)
    )
    results['summary'] = {
        'success': all(item.get('success', True) for item in results.values()),
        'total_analyzed': analyzed_count,
        'message': f'班级 {class_id} 共分析 {analyzed_count} 条数据',
    }
    return results
```

删除 Web 端 `/api/import/clear-all` 和对应按钮，数据库清空只保留 Task 8 的 CLI 命令。

- [ ] **Step 7: 更新上传页面**

通用导入页显示活动班级下拉框，默认当前班级；班级详情页上传按钮固定传入详情班级。收到 409 冲突时显示识别班级和目标班级，用户确认后设置 `confirm_class_mismatch=true` 重传同一文件。

- [ ] **Step 8: 运行导入测试**

Run: `pytest tests/test_class_imports.py tests/test_class_isolation.py -q`

Expected: 全部 PASS。

- [ ] **Step 9: 提交**

```bash
git add services/importers/base_importer.py services/importers/rainclass_importer.py services/importers/educoder_importer.py controllers/import_controller.py templates/import/index.html templates/class/detail.html tests/test_class_imports.py
git commit -m "feat: bind imports and analysis to classes"
```

---

### Task 6: 完成单班页面状态、班级标签与空数据体验

**Files:**
- Create: `tests/test_class_pages.py`
- Modify: `templates/base.html`
- Modify: `templates/dashboard/index.html`
- Modify: `templates/student/list.html`
- Modify: `templates/student/detail.html`
- Modify: `templates/student/overview.html`
- Modify: `templates/knowledge/index.html`
- Modify: `templates/warning/index.html`
- Modify: `templates/import/index.html`

**Interfaces:**
- Consumes: 模板变量 `active_class`、`active_classes`。
- Produces: 所有业务页可见当前班级，空数据状态提供班级内上传链接。

- [ ] **Step 1: 写页面状态失败测试**

创建 `tests/test_class_pages.py`：

```python
def login_and_select(client, class_id):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    client.post(f'/api/classes/{class_id}/select')


def test_pages_show_active_class(client, two_classes):
    first_id, _ = two_classes
    login_and_select(client, first_id)
    for path in ['/', '/students', '/knowledge', '/warning', '/import']:
        response = client.get(path)
        assert response.status_code == 200
        assert '青年1班' in response.get_data(as_text=True)


def test_page_without_active_class_redirects_to_classes(client):
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    response = client.get('/students')
    assert response.status_code == 302
    assert '/classes' in response.headers['Location']
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_class_pages.py -q`

Expected: FAIL，业务页尚未显示当前班级或未强制选择。

- [ ] **Step 3: 添加统一班级页头**

在 `base.html` 内容区上方渲染：

```html
{% if active_class %}
<div class="content-header pb-0">
  <div class="container-fluid d-flex justify-content-between align-items-center">
    <div><span class="text-muted">当前班级</span> <strong>{{ active_class.class_name }}</strong></div>
    <a class="btn btn-sm btn-outline-primary" href="{{ url_for('classes.index') }}">切换班级</a>
  </div>
</div>
{% endif %}
```

- [ ] **Step 4: 统一 AJAX 错误处理**

在 `base.html` 增加：

```javascript
$(document).ajaxError(function(_event, xhr) {
  if (xhr.status === 401) {
    window.location.href = '/login';
  } else if (xhr.status === 409 && xhr.responseJSON && xhr.responseJSON.error === 'active_class_required') {
    window.location.href = '/classes';
  }
});
```

各页面在返回空数组或零学生时显示“当前班级暂无数据”，并链接到 `url_for('import.import_page')`；不得复用其他班级数据填充图表。

- [ ] **Step 5: 更新页面文案与导航状态**

逐页把“全体学生”“全年级”等文案改为“当前班级”；列表和图表标题包含 `active_class.class_name`。班级管理和班级对比导航使用对应 endpoint 判断 active 状态。

- [ ] **Step 6: 运行页面测试**

Run: `pytest tests/test_class_pages.py -q`

Expected: `2 passed`。

- [ ] **Step 7: 提交**

```bash
git add templates/base.html templates/dashboard/index.html templates/student/list.html templates/student/detail.html templates/student/overview.html templates/knowledge/index.html templates/warning/index.html templates/import/index.html tests/test_class_pages.py
git commit -m "feat: show active class across all pages"
```

---

### Task 7: 实现独立班级对比页面

**Files:**
- Create: `services/class_comparison.py`
- Create: `templates/class/compare.html`
- Create: `tests/test_class_comparison.py`
- Modify: `controllers/class_controller.py`
- Modify: `templates/base.html`

**Interfaces:**
- Produces: `ClassComparisonService.compare(class_ids: list[int]) -> list[dict]`。
- Produces: `GET /class-compare`、`GET /api/classes/compare?class_id=1&class_id=2`。

- [ ] **Step 1: 写对比口径失败测试**

创建 `tests/test_class_comparison.py`：

```python
from models import Student, StudentBehavior, StudentPractice, WarningRecord, db


def test_compare_returns_separate_metrics(app, client, two_classes):
    first_id, second_id = two_classes
    with app.app_context():
        first = Student(student_no='20260001', name='甲', class_id=first_id)
        second = Student(student_no='20260002', name='乙', class_id=second_id)
        db.session.add_all([first, second])
        db.session.flush()
        db.session.add_all([
            StudentBehavior(student_id=first.id, attendance_rate=90),
            StudentBehavior(student_id=second.id, attendance_rate=50),
            StudentPractice(student_id=first.id, avg_experiment_score=80),
            StudentPractice(student_id=second.id, avg_experiment_score=60),
            WarningRecord(student_id=second.id, warning_type='综合', warning_level=2, warning_score=70),
        ])
        db.session.commit()

    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    response = client.get(f'/api/classes/compare?class_id={first_id}&class_id={second_id}')
    assert response.status_code == 200
    rows = response.get_json()
    assert [row['class_id'] for row in rows] == [first_id, second_id]
    assert rows[0]['student_count'] == 1
    assert rows[0]['avg_attendance_rate'] == 90
    assert rows[1]['warning_rate'] == 100
    assert 'students' not in rows[0]


def test_compare_requires_two_classes(client, two_classes):
    first_id, _ = two_classes
    client.post('/login', data={'username': 'admin', 'password': 'correct-password'})
    response = client.get(f'/api/classes/compare?class_id={first_id}')
    assert response.status_code == 400
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_class_comparison.py -q`

Expected: FAIL，对比路由不存在。

- [ ] **Step 3: 实现只返回聚合值的对比服务**

创建 `services/class_comparison.py`：

```python
from repositories import BehaviorRepository, KnowledgeRepository, StudentRepository, WarningRepository
from services.analysis import PracticeAnalyzer
from models import ClassInfo


class ClassComparisonService:
    @staticmethod
    def compare(class_ids: list[int]) -> list[dict]:
        if len(set(class_ids)) < 2:
            raise ValueError('至少选择两个不同班级')
        rows = []
        for class_id in class_ids:
            class_info = ClassInfo.query.filter_by(id=class_id).first()
            if class_info is None:
                raise ValueError(f'班级不存在: {class_id}')
            behavior = BehaviorRepository.get_statistics(class_id)
            practice = PracticeAnalyzer(class_id).get_class_statistics(class_id)
            knowledge = KnowledgeRepository.get_knowledge_statistics(class_id)
            warnings = WarningRepository.get_statistics(class_id)
            student_count = StudentRepository.get_count(class_id)
            avg_mastery = (
                sum(item['avg_mastery_rate'] for item in knowledge) / len(knowledge)
                if knowledge else None
            )
            warning_count = warnings['warning_student_count']
            rows.append({
                'class_id': class_id,
                'class_name': class_info.class_name,
                'student_count': student_count,
                'avg_attendance_rate': behavior['avg_attendance_rate'],
                'avg_practice_score': practice['avg_experiment_score'],
                'avg_mastery_rate': round(avg_mastery, 2) if avg_mastery is not None else None,
                'warning_count': warning_count,
                'warning_rate': round(warning_count / student_count * 100, 2) if student_count else 0,
            })
        return rows
```

若 `PracticeAnalyzer.get_class_statistics` 的现有返回键不同，在本任务内统一为 `avg_experiment_score`，并更新对应单班调用，确保同一口径。

同时将 `WarningRepository.get_statistics(class_id)` 的人数指标实现为：

```python
warning_student_count = db.session.query(func.count(func.distinct(WarningRecord.student_id))).join(
    Student, WarningRecord.student_id == Student.id
).filter(Student.class_id == class_id, WarningRecord.warning_score >= 60).scalar() or 0
```

返回字典使用 `warning_student_count`，Dashboard 和对比服务都复用该值，避免把一个学生的多条预警重复计数。

- [ ] **Step 4: 实现路由和页面**

`GET /class-compare` 渲染活动与归档班级多选；`GET /api/classes/compare` 用 `request.args.getlist('class_id', type=int)` 读取班级，少于两个不同班级返回 400。页面使用 ECharts 柱状图/雷达图显示聚合指标，并保留数值表格；不得展示学生列表。

- [ ] **Step 5: 运行对比测试**

Run: `pytest tests/test_class_comparison.py -q`

Expected: `2 passed`。

- [ ] **Step 6: 提交**

```bash
git add services/class_comparison.py controllers/class_controller.py templates/class/compare.html templates/base.html tests/test_class_comparison.py
git commit -m "feat: add explicit class comparison"
```

---

### Task 8: 实现受控数据库重建、配置说明与最终验收

**Files:**
- Create: `tests/test_database_reset.py`
- Modify: `init_database.py`
- Modify: `README.md`
- Modify: `start.bat`
- Modify: `start.sh`

**Interfaces:**
- Produces: `python init_database.py --reset --confirm-reset DELETE-ALL-STUDENT-ANALYSIS-DATA`。
- Produces: 无确认参数时退出码 `2`，不连接或删除数据库。

- [ ] **Step 1: 写重建保护失败测试**

创建 `tests/test_database_reset.py`：

```python
from init_database import RESET_CONFIRMATION, validate_reset_confirmation


def test_reset_requires_exact_confirmation():
    assert validate_reset_confirmation(None) is False
    assert validate_reset_confirmation('yes') is False
    assert validate_reset_confirmation(RESET_CONFIRMATION) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_database_reset.py -q`

Expected: FAIL，确认常量与校验函数不存在。

- [ ] **Step 3: 实现非交互显式确认**

在 `init_database.py` 加入：

```python
RESET_CONFIRMATION = 'DELETE-ALL-STUDENT-ANALYSIS-DATA'


def validate_reset_confirmation(value: str | None) -> bool:
    return value == RESET_CONFIRMATION
```

参数定义改为：

```python
parser.add_argument('--reset', action='store_true', help='删除并重建数据库')
parser.add_argument('--confirm-reset', help=f'重建时必须精确输入 {RESET_CONFIRMATION}')
```

在调用任何删除逻辑前检查：

```python
if args.reset and not validate_reset_confirmation(args.confirm_reset):
    parser.error(f'--reset 必须同时提供 --confirm-reset {RESET_CONFIRMATION}')
```

删除 `input()` 交互确认；只有通过精确参数校验后才能执行 `DROP DATABASE`。`create_tables()` 使用生产/开发配置创建当前全部模型表，不创建示例班级或默认账号。

- [ ] **Step 4: 更新部署和首次导入说明**

在 `README.md` 写明：

```text
1. 设置 ADMIN_USERNAME。
2. 使用 Werkzeug generate_password_hash 生成 ADMIN_PASSWORD_HASH。
3. 设置随机 SECRET_KEY；HTTPS 部署设置 SESSION_COOKIE_SECURE=true。
4. 首次结构升级执行：python init_database.py --reset --confirm-reset DELETE-ALL-STUDENT-ANALYSIS-DATA。
5. 启动后登录，创建两个班级，分别进入班级详情上传 Excel。
6. 检查两个班级的首页、学生、知识、预警与班级对比。
```

同步更新 `start.bat` 和 `start.sh` 的必需环境变量检查；缺少管理员账号、密码哈希或生产 `SECRET_KEY` 时输出明确错误并退出，不写入默认值。

- [ ] **Step 5: 运行全套测试**

Run: `pytest -q`

Expected: 所有 `tests/` 测试 PASS；现有根目录解析测试不因构造函数签名变化而失败。

- [ ] **Step 6: 运行静态与语法检查**

Run: `python -m compileall app.py config.py controllers models repositories services tests`

Expected: 命令退出码为 0，无 `SyntaxError`。

Run: `rg -n "ClassInfo\.get_by_name|_get_or_create_class|ImportRecord\.is_imported\([^,]+\)|BehaviorAnalyzer\(\)|KnowledgeAnalyzer\(\)|PracticeAnalyzer\(\)|WarningEngine\(\)|/api/import/clear-all" controllers repositories services templates`

Expected: 无旧的自动建班、单参数导入去重、无班级分析器或 Web 清库入口。

- [ ] **Step 7: 使用两个班级完成手工验收**

在独立测试数据库执行以下验收，不在用户现有数据库上直接运行重建：

1. 创建“青年1班”和“青年2班”。
2. 分别上传各自雨课堂和头歌 Excel。
3. 切换到青年1班，记录首页学生数、学生列表首尾学号、知识点数和预警数。
4. 切换到青年2班，确认上述数据全部随班级变化，搜索青年1班学生返回空。
5. 手工请求青年1班学生详情 ID，确认在青年2班上下文返回 404。
6. 打开班级对比页，确认两个班的聚合值分别等于各自首页值。
7. 归档一个班，确认其离开快速切换列表但仍可在管理页恢复。

- [ ] **Step 8: 提交**

```bash
git add init_database.py README.md start.bat start.sh tests/test_database_reset.py
git commit -m "docs: add controlled reset and deployment workflow"
```

---

## 最终完成条件

- `pytest -q` 全部通过。
- `python -m compileall app.py config.py controllers models repositories services tests` 退出码为 0。
- 静态扫描不存在无班级参数的普通查询、分析器调用、自动创建班级或 Web 清库入口。
- 两套 Excel 在两个班级中重新导入成功，普通页面没有跨班数据，班级对比口径一致。
- 管理员凭据缺失时系统安全拒绝访问，正确凭据登录后才能选择班级并使用业务功能。
