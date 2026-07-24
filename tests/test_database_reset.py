import pytest
from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import init_database
from init_database import RESET_CONFIRMATION, validate_reset_confirmation


def test_reset_requires_exact_confirmation():
    assert validate_reset_confirmation(None) is False
    assert validate_reset_confirmation('yes') is False
    assert validate_reset_confirmation(RESET_CONFIRMATION) is True


def test_reset_module_uses_python39_compatible_type_annotations():
    source = (Path(__file__).parents[1] / 'init_database.py').read_text(encoding='utf-8')

    assert 'str | None' not in source


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


def test_cli_rejects_unconfirmed_reset_before_importing_database_dependencies():
    project_root = Path(__file__).parents[1]
    probe = textwrap.dedent(
        f"""
        import runpy
        import sys

        class BlockDatabaseDependencies:
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {{'app', 'models'}}:
                    raise RuntimeError('database dependency imported before reset validation')
                return None

        sys.meta_path.insert(0, BlockDatabaseDependencies())
        sys.argv = ['init_database.py', '--reset']
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


@pytest.mark.parametrize('script_name', ['start.bat', 'start.sh'])
def test_start_scripts_validate_credentials_before_database_access(script_name):
    script = (Path(__file__).parents[1] / script_name).read_text(encoding='utf-8')

    assert 'ADMIN_USERNAME' in script
    assert 'ADMIN_PASSWORD_HASH' in script
    assert 'SECRET_KEY' in script
    assert 'FLASK_ENV' in script
    assert 'SESSION_COOKIE_SECURE' in script
    assert script.index('ADMIN_USERNAME') < script.index('pymysql.connect')
    assert script.index('ADMIN_PASSWORD_HASH') < script.index('pymysql.connect')
    assert script.index('SECRET_KEY') < script.index('pymysql.connect')
    assert 'Root@123456' not in script
    assert '--reset' not in script


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
