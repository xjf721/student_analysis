import ast
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

import init_database
from init_database import RESET_CONFIRMATION, validate_reset_confirmation


KNOWN_DATABASE_CREDENTIAL = 'Root@' + '123456'


def test_reset_requires_exact_confirmation():
    assert validate_reset_confirmation(None) is False
    assert validate_reset_confirmation('yes') is False
    assert validate_reset_confirmation(RESET_CONFIRMATION) is True


def test_reset_module_uses_python39_compatible_type_annotations():
    source = (Path(__file__).parents[1] / 'init_database.py').read_text(encoding='utf-8')

    ast.parse(source, filename='init_database.py', feature_version=(3, 9))


@pytest.mark.parametrize('arguments', [
    ['--reset'],
    ['--reset', '--confirm-reset', 'yes'],
])
def test_invalid_reset_confirmation_exits_before_database_operations(monkeypatch, arguments):
    def unexpected_operation():
        raise AssertionError('database operations must not run before confirmation validation')

    monkeypatch.setattr(init_database, 'reset_database', unexpected_operation)
    monkeypatch.setattr(init_database, 'create_database', unexpected_operation)
    monkeypatch.setattr(init_database, 'create_tables', unexpected_operation)

    with pytest.raises(SystemExit) as error:
        init_database.main(arguments)

    assert error.value.code == 2


@pytest.mark.parametrize('confirmation_args', [
    [],
    ['--confirm-reset', 'yes'],
])
def test_cli_rejects_unconfirmed_reset_before_importing_database_dependencies(
        tmp_path, confirmation_args):
    project_root = Path(__file__).parents[1]
    dependency_marker = tmp_path / 'database-dependency-imported'
    connection_marker = tmp_path / 'database-connection-attempted'
    probe = textwrap.dedent(
        f"""
        import os
        import runpy
        import socket
        import sys
        from pathlib import Path

        def reject_connection(*args, **kwargs):
            Path({str(connection_marker)!r}).write_text('connect', encoding='utf-8')
            raise RuntimeError('network connection attempted before reset validation')

        socket.create_connection = reject_connection

        class BlockDatabaseDependencies:
            def find_spec(self, fullname, path=None, target=None):
                blocked_prefixes = (
                    'config', 'pymysql', 'app', 'models',
                    'sqlalchemy', 'flask_sqlalchemy', 'mysql',
                )
                if any(fullname == prefix or fullname.startswith(prefix + '.')
                       for prefix in blocked_prefixes):
                    Path({str(dependency_marker)!r}).write_text(fullname, encoding='utf-8')
                    raise RuntimeError('database dependency imported before reset validation')
                return None

        os.environ['MYSQL_PORT'] = 'not-a-port'
        sys.meta_path.insert(0, BlockDatabaseDependencies())
        sys.argv = ['init_database.py', '--reset'] + {confirmation_args!r}
        runpy.run_path({str(project_root / 'init_database.py')!r}, run_name='__main__')
        """
    )

    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert RESET_CONFIRMATION in result.stderr
    assert 'database dependency imported before reset validation' not in result.stderr
    assert not dependency_marker.exists()
    assert not connection_marker.exists()


def test_confirmed_reset_runs_reset_before_table_creation(monkeypatch):
    operations = []
    monkeypatch.setattr(init_database, 'reset_database', lambda: operations.append('reset') or True)
    monkeypatch.setattr(init_database, 'create_tables', lambda: operations.append('tables') or True)
    monkeypatch.setattr(
        init_database,
        'create_database',
        lambda: (_ for _ in ()).throw(AssertionError('reset must not use normal database creation')),
    )

    init_database.main(['--reset', '--confirm-reset', RESET_CONFIRMATION])

    assert operations == ['reset', 'tables']


def test_normal_startup_never_resets_database(monkeypatch):
    operations = []
    monkeypatch.setattr(
        init_database,
        'reset_database',
        lambda: (_ for _ in ()).throw(AssertionError('normal startup must never reset the database')),
    )
    monkeypatch.setattr(init_database, 'create_tables', lambda: operations.append('tables') or True)

    init_database.main(['--tables-only'])

    assert operations == ['tables']


@pytest.mark.parametrize(('script_name', 'required_fragments'), [
    ('start.bat', [
        'if not defined ADMIN_USERNAME',
        'if not defined ADMIN_PASSWORD_HASH',
        'if not defined MYSQL_USER',
        'if not defined MYSQL_PASSWORD',
    ]),
    ('start.sh', [
        'require_env ADMIN_USERNAME',
        'require_env ADMIN_PASSWORD_HASH',
        'require_env MYSQL_USER',
        'require_env MYSQL_PASSWORD',
    ]),
])
def test_start_scripts_validate_credentials_before_database_access(
        script_name, required_fragments):
    script = (Path(__file__).parents[1] / script_name).read_text(encoding='utf-8')

    for fragment in required_fragments:
        assert fragment in script
    assert 'SECRET_KEY' in script
    assert 'FLASK_ENV' in script
    assert 'SESSION_COOKIE_SECURE' in script
    assert script.index('ADMIN_USERNAME') < script.index('pymysql.connect')
    assert script.index('ADMIN_PASSWORD_HASH') < script.index('pymysql.connect')
    assert script.index('SECRET_KEY') < script.index('pymysql.connect')
    assert 'validate_database_environment' in script
    assert script.index('validate_database_environment') < script.index('pymysql.connect')
    assert KNOWN_DATABASE_CREDENTIAL not in script
    assert '--reset' not in script


@pytest.mark.parametrize('missing_variable', ['MYSQL_USER', 'MYSQL_PASSWORD'])
def test_missing_mysql_credentials_fail_before_database_initialization(
        monkeypatch, missing_variable):
    import app as app_module

    monkeypatch.setenv('MYSQL_USER', 'application-user')
    monkeypatch.setenv('MYSQL_PASSWORD', 'not-a-real-password')
    monkeypatch.delenv(missing_variable)
    database_touched = False

    def fail_if_database_is_initialized(_app):
        nonlocal database_touched
        database_touched = True
        raise AssertionError('database initialization must not occur')

    monkeypatch.setattr(app_module, 'init_db', fail_if_database_is_initialized)

    with pytest.raises(RuntimeError, match=missing_variable):
        app_module.create_app('dev')

    assert database_touched is False


def test_tracked_repository_has_no_known_database_credential():
    project_root = Path(__file__).parents[1]
    tracked = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=project_root,
        capture_output=True,
        check=True,
    ).stdout.decode().split('\0')
    offenders = []

    for relative_path in filter(None, tracked):
        path = project_root / relative_path
        try:
            contents = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        if KNOWN_DATABASE_CREDENTIAL in contents:
            offenders.append(relative_path)

    assert offenders == []


def test_production_start_uses_waitress_and_app_never_forces_debug():
    project_root = Path(__file__).parents[1]
    app_source = (project_root / 'app.py').read_text(encoding='utf-8')
    requirements = (project_root / 'requirements.txt').read_text(encoding='utf-8')
    readme = (project_root / 'README.md').read_text(encoding='utf-8')

    assert 'debug=True' not in app_source
    assert 'Waitress==' in requirements
    assert 'Waitress' in readme
    for script_name in ['start.bat', 'start.sh']:
        script = (project_root / script_name).read_text(encoding='utf-8')
        assert '-m waitress --listen=0.0.0.0:5000 app:app' in script


def test_production_application_disables_debug(tmp_path):
    from app import create_app

    production_app = create_app('prod', overrides={
        'SQLALCHEMY_DATABASE_URI': f"sqlite:///{tmp_path / 'production-debug.db'}",
        'SECRET_KEY': 'production-test-secret',
    })

    assert production_app.debug is False


def test_create_tables_uses_runtime_environment_config(monkeypatch):
    selected_configs = []

    class AppContext:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake_app = SimpleNamespace(app_context=lambda: AppContext())
    fake_db = SimpleNamespace(create_all=lambda: None, engine=object())
    fake_inspector = SimpleNamespace(get_table_names=lambda: ['classes', 'students'])

    monkeypatch.setenv('FLASK_ENV', 'prod')
    fake_create_app = lambda config_name: selected_configs.append(config_name) or fake_app
    monkeypatch.setattr(
        init_database,
        'load_app_dependencies',
        lambda: (fake_create_app, fake_db),
    )
    monkeypatch.setattr('sqlalchemy.inspect', lambda _engine: fake_inspector)

    assert init_database.create_tables() is True
    assert selected_configs == ['prod']


def test_readme_documents_controlled_reset_and_first_run_acceptance():
    readme = (Path(__file__).parents[1] / 'README.md').read_text(encoding='utf-8')

    required_guidance = [
        'ADMIN_USERNAME',
        'ADMIN_PASSWORD_HASH',
        'generate_password_hash',
        'SECRET_KEY',
        'SESSION_COOKIE_SECURE=true',
        f'python init_database.py --reset --confirm-reset {RESET_CONFIRMATION}',
        '青年1班',
        '青年2班',
        '班级对比',
        '归档',
    ]
    for guidance in required_guidance:
        assert guidance in readme
