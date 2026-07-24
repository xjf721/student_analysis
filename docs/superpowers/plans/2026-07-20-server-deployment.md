# Server Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, repeatable Docker Compose release for the Flask teaching-analysis application that joins an existing reverse-proxy container network and starts with an empty MySQL database.

**Architecture:** A production-only WSGI entry point runs Flask under Gunicorn in a stateless Web container. A private MySQL 8 container owns persistent database storage; Web also joins a pre-existing external proxy network, while no project container publishes a host port. Cross-platform release tooling creates a strict allowlist archive, and Bash operations scripts handle validation, backup, deployment, rollback preparation, and guarded restore.

**Tech Stack:** Python 3.11, Flask 3.0, Gunicorn 22, SQLAlchemy 2.0, MySQL 8.4 LTS, Docker Compose v2, Bash, Python `unittest`.

## Global Constraints

- Target: one Linux server with Docker Compose v2 and a configured domestic registry mirror.
- Access: campus network through an existing reverse-proxy Docker container.
- Containers: only `student-analysis-web` and `student-analysis-db`; do not add another reverse proxy.
- Networking: publish no Web or MySQL host ports; Web joins external `PROXY_NETWORK`, MySQL remains private.
- Persistence: named volumes for MySQL, uploads, and auxiliary logs; releases must not replace these volumes.
- First deployment: empty database; users import data through the application after deployment.
- Secrets: production startup fails when `SECRET_KEY`, `MYSQL_PASSWORD`, or required proxy settings are missing or example values.
- Release privacy: never package `.git`, `.env`, logs, uploads, backups, database dumps, archives, or `.xls`/`.xlsx` files.
- Database safety: production scripts never invoke `init_database.py --reset`; no destructive migration is allowed in this release.
- Runtime: Gunicorn defaults to 2 workers, 4 threads per worker, and 120-second timeout.
- Health: `/health` returns 200 only when the application and database are available; database failure returns 503 without sensitive details.
- Existing unrelated working-tree changes belong to the user and must not be modified or committed.

---

## File Map

**Create:**

- `wsgi.py` — production-only Gunicorn entry point.
- `requirements-prod.txt` — pinned runtime dependencies only.
- `tests/test_production_runtime.py` — configuration, import-safety, and WSGI behavior tests.
- `tests/test_health.py` — health response and database-failure tests.
- `tests/test_deployment_assets.py` — Compose, Dockerfile, environment-template, and release-policy tests.
- `tests/test_release_export.py` — archive allowlist and checksum tests.
- `Dockerfile` — non-root production image.
- `.dockerignore` — Docker build-context privacy boundary.
- `compose.yaml` — Web/MySQL services, networks, health checks, and named volumes.
- `.env.example` — documented required deployment variables with non-secret examples.
- `scripts/ops_common.sh` — shared validation, Compose, wait, and path-safety functions.
- `scripts/install_release.sh` — checksum verification and safe extraction into the versioned release directory.
- `scripts/deploy.sh` — first deployment and upgrade orchestration.
- `scripts/backup.sh` — MySQL and uploads backup.
- `scripts/restore.sh` — explicitly confirmed restore.
- `scripts/export_release.py` — cross-platform allowlist packager and SHA-256 generator.
- `DEPLOY.md` — server setup, proxy integration, operations, verification, and recovery runbook.

**Modify:**

- `config.py` — environment-derived production configuration and fail-fast validation.
- `app.py` — remove import-time application creation, register health check, and use production-safe logging.
- `models/base.py` — use application configuration and fail closed on database bootstrap errors.
- `init_database.py` — select production configuration explicitly and preserve reset as a manual development-only action.
- `export.sh` — thin Linux/WSL wrapper around `scripts/export_release.py`.
- `export.bat` — thin Windows wrapper around `scripts/export_release.py`.
- `.gitignore` — ignore generated release archives and local deployment environment files without hiding templates.

---

### Task 1: Production Configuration and Import-Safe App Factory

**Files:**

- Create: `tests/test_production_runtime.py`
- Create: `wsgi.py`
- Modify: `config.py:5-110`
- Modify: `app.py:18-114`

**Interfaces:**

- Produces: `validate_production_config(values: Mapping[str, Any]) -> None` in `config.py`.
- Produces: `create_app(config_name: str = "dev") -> Flask` without import-time database access.
- Produces: `wsgi.app`, the Gunicorn application object created with `create_app("prod")`.
- Consumes: environment keys `SECRET_KEY`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, and optional `EDUCODER_ASSIGNMENT_FILE`.

- [ ] **Step 1: Write failing production-runtime tests**

```python
# tests/test_production_runtime.py
import importlib
import unittest
from unittest.mock import patch

from config import validate_production_config


class ProductionConfigValidationTest(unittest.TestCase):
    def valid_config(self):
        return {
            "SECRET_KEY": "c" * 48,
            "MYSQL_PASSWORD": "strong-db-password",
            "MYSQL_USER": "student_analysis",
            "MYSQL_DATABASE": "student_analysis",
        }

    def test_rejects_missing_secret_key(self):
        values = self.valid_config()
        values["SECRET_KEY"] = ""
        with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
            validate_production_config(values)

    def test_rejects_example_database_password(self):
        values = self.valid_config()
        values["MYSQL_PASSWORD"] = "change-me"
        with self.assertRaisesRegex(RuntimeError, "MYSQL_PASSWORD"):
            validate_production_config(values)

    def test_accepts_complete_values(self):
        validate_production_config(self.valid_config())

    def test_importing_app_module_does_not_create_application(self):
        with patch("models.init_db") as init_db:
            module = importlib.reload(importlib.import_module("app"))
        self.assertFalse(hasattr(module, "app"))
        init_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm the missing validator/import side effect failures**

Run: `python -m unittest tests.test_production_runtime -v`

Expected: FAIL because `validate_production_config` is absent and `app.py` still creates `app` at import time.

- [ ] **Step 3: Refactor configuration and the application entry point**

Add this validator and explicit production fields to `config.py`, retaining existing warning rules unchanged:

```python
from typing import Any, Mapping
from urllib.parse import quote_plus

EXAMPLE_SECRETS = {
    "",
    "change-me",
    "dev-secret-key-change-in-production",
}


def build_database_uri(host: str, port: int, user: str, password: str, database: str) -> str:
    encoded_password = quote_plus(password)
    return (
        f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/"
        f"{database}?charset=utf8mb4"
    )


def validate_production_config(values: Mapping[str, Any]) -> None:
    invalid = [
        key
        for key in ("SECRET_KEY", "MYSQL_PASSWORD")
        if str(values.get(key, "")).strip() in EXAMPLE_SECRETS
    ]
    missing = [
        key
        for key in ("MYSQL_USER", "MYSQL_DATABASE")
        if not str(values.get(key, "")).strip()
    ]
    errors = invalid + missing
    if errors:
        raise RuntimeError(
            "Production configuration is missing or unsafe: " + ", ".join(errors)
        )
```

Define `Config` fields from environment and override only development defaults:

```python
class Config:
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
    MYSQL_USER = os.environ.get("MYSQL_USER", "student_analysis")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "student_analysis")
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = build_database_uri(
        MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False
    AUTO_CREATE_DATABASE = False
    UPLOAD_FOLDER = str(Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "uploads")))
    LOG_FOLDER = str(Path(os.environ.get("LOG_FOLDER", BASE_DIR / "logs")))
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    EDUCODER_ASSIGNMENT_FILE = os.environ.get("EDUCODER_ASSIGNMENT_FILE", "")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True
    AUTO_CREATE_DATABASE = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    MYSQL_USER = os.environ.get("MYSQL_USER", "")
    MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = build_database_uri(
        Config.MYSQL_HOST, Config.MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, Config.MYSQL_DATABASE
    )


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AUTO_CREATE_DATABASE = False
```

In `app.py`, validate before database initialization and remove the module-level `app`:

```python
from config import config_by_name, validate_production_config


def create_app(config_name: str = "dev") -> Flask:
    if config_name not in config_by_name:
        raise ValueError(f"Unknown configuration: {config_name}")
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])
    if config_name == "prod":
        validate_production_config(app.config)
    ensure_directories(app)
    setup_logging(app)
    init_db(app)
    register_blueprints(app)
    register_error_handlers(app)
    return app


if __name__ == "__main__":
    development_app = create_app("dev")
    development_app.run(host="0.0.0.0", port=5000, debug=True)
```

Create the production entry point:

```python
# wsgi.py
from app import create_app

app = create_app("prod")
```

- [ ] **Step 4: Run production-runtime tests**

Run: `python -m unittest tests.test_production_runtime -v`

Expected: 4 tests PASS; importing `app` does not initialize a database.

- [ ] **Step 5: Commit Task 1 only**

```bash
git add config.py app.py wsgi.py tests/test_production_runtime.py
git commit -m "refactor: add production-safe application entry point"
```

---

### Task 2: Fail-Closed Database Bootstrap and Health Endpoint

**Files:**

- Create: `tests/test_health.py`
- Modify: `models/base.py:15-100`
- Modify: `init_database.py:121-176`
- Modify: `app.py:42-106`

**Interfaces:**

- Consumes: `AUTO_CREATE_DATABASE`, `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` from Flask config.
- Produces: `register_health_check(app: Flask) -> None` and `GET /health` JSON.
- Produces: `create_tables(config_name: str = "prod") -> bool`.

- [ ] **Step 1: Write failing bootstrap and health tests**

```python
# tests/test_health.py
import unittest
from unittest.mock import patch

from flask import Flask

from app import register_health_check
from models import db
from models.base import ensure_database_exists


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        register_health_check(self.app)

    def test_health_returns_200_when_database_responds(self):
        response = self.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_health_returns_503_without_exception_details(self):
        with patch.object(db.session, "execute", side_effect=RuntimeError("secret")):
            response = self.app.test_client().get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "unavailable"})
        self.assertNotIn(b"secret", response.data)

    def test_database_bootstrap_raises_when_connection_fails(self):
        app = Flask(__name__)
        app.config.update(
            MYSQL_HOST="db",
            MYSQL_PORT=3306,
            MYSQL_USER="student_analysis",
            MYSQL_PASSWORD="safe-password",
            MYSQL_DATABASE="student_analysis",
        )
        with patch("models.base.pymysql.connect", side_effect=OSError("offline")):
            with self.assertRaisesRegex(RuntimeError, "database bootstrap"):
                ensure_database_exists(app)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify expected failures**

Run: `python -m unittest tests.test_health -v`

Expected: FAIL because `register_health_check` does not exist and database bootstrap swallows failures.

- [ ] **Step 3: Implement fail-closed bootstrap and health registration**

Change `models/base.py` to use app configuration and re-raise safely:

```python
def ensure_database_exists(app) -> None:
    try:
        connection = pymysql.connect(
            host=app.config["MYSQL_HOST"],
            port=app.config["MYSQL_PORT"],
            user=app.config["MYSQL_USER"],
            password=app.config["MYSQL_PASSWORD"],
            charset="utf8mb4",
        )
        with connection:
            with connection.cursor() as cursor:
                database = app.config["MYSQL_DATABASE"]
                cursor.execute(
                    "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                    "WHERE SCHEMA_NAME = %s",
                    (database,),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci"
                    )
                    connection.commit()
    except Exception as exc:
        app.logger.exception("Database bootstrap failed")
        raise RuntimeError("database bootstrap failed") from exc


def init_db(app) -> None:
    if app.config.get("AUTO_CREATE_DATABASE", False):
        ensure_database_exists(app)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        ensure_schema_columns()
```

Register health before returning the app:

```python
from flask import jsonify
from sqlalchemy import text
from models import db


def register_health_check(app: Flask) -> None:
    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            app.logger.exception("Health check database probe failed")
            return jsonify(status="unavailable"), 503
        return jsonify(status="ok"), 200
```

Call `register_health_check(app)` after `init_db(app)`. Refactor `init_database.py` so `create_database(config_name)`, `reset_database(config_name)`, and `create_tables(config_name="prod")` read values from `config_by_name[config_name]` instead of importing removed module-level constants; pass `os.environ.get("FLASK_ENV", "prod")` from `main()`. Keep `--reset` available only when `config_name == "dev"`; otherwise print an error and exit 2 before calling `reset_database`.

Replace the unbounded `FileHandler` in `setup_logging` with a rotating handler while retaining standard output:

```python
from logging.handlers import RotatingFileHandler


def setup_logging(app: Flask) -> None:
    log_folder = Path(app.config["LOG_FOLDER"])
    log_folder.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = RotatingFileHandler(
        log_folder / "system.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))
```

- [ ] **Step 4: Run focused and existing lightweight tests**

Run: `python -m unittest tests.test_health tests.test_production_runtime -v`

Expected: 7 tests PASS.

Run: `python test_column_mapping.py`

Expected: process exits 0 and prints `测试完成!`.

- [ ] **Step 5: Commit Task 2 only**

```bash
git add app.py models/base.py init_database.py tests/test_health.py
git commit -m "feat: add database-aware health checks"
```

---

### Task 3: Production Image and Compose Topology

**Files:**

- Create: `requirements-prod.txt`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `compose.yaml`
- Create: `.env.example`
- Create: `tests/test_deployment_assets.py`

**Interfaces:**

- Consumes: `wsgi.app`, `/health`, and all `.env.example` variables.
- Produces: Compose services `web`/`db`, containers `student-analysis-web`/`student-analysis-db`, external network `${PROXY_NETWORK}`, and volumes `student-analysis-db-data`, `student-analysis-uploads`, `student-analysis-logs`.

- [ ] **Step 1: Write failing static deployment-asset tests**

```python
# tests/test_deployment_assets.py
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentAssetsTest(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_compose_has_no_host_ports_and_uses_external_proxy_network(self):
        compose = self.read("compose.yaml")
        self.assertNotIn("ports:", compose)
        self.assertIn("name: ${PROXY_NETWORK:?PROXY_NETWORK is required}", compose)
        self.assertIn("external: true", compose)
        self.assertIn("student-analysis-db-data", compose)

    def test_dockerfile_is_non_root_and_runs_gunicorn(self):
        dockerfile = self.read("Dockerfile")
        self.assertIn("USER app", dockerfile)
        self.assertIn("gunicorn", dockerfile)
        self.assertNotIn("python app.py", dockerfile)

    def test_environment_template_contains_no_real_secret(self):
        environment = self.read(".env.example")
        self.assertIn("PROXY_NETWORK=reverse-proxy", environment)
        self.assertIn("PROXY_CONTAINER=reverse-proxy", environment)
        self.assertNotIn("MYSQL_PASSWORD=change-me", environment)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm missing-file failures**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: ERROR with `FileNotFoundError` for the new deployment assets.

- [ ] **Step 3: Add pinned production dependencies and non-root image**

Create `requirements-prod.txt` with the runtime packages from `requirements.txt`, omit `flask-shell-ipython`, and add `gunicorn==22.0.0`.

Create `Dockerfile`:

```dockerfile
FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY --chown=app:app . .
RUN mkdir -p /app/uploads /app/logs && chown -R app:app /app/uploads /app/logs
USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-120} --access-logfile - --error-logfile - wsgi:app"]
```

Create `.dockerignore` with `.git`, `.agents`, `.env`, `.env.*`, `!.env.example`, `venv`, `.venv`, `__pycache__`, `*.pyc`, `*.xls`, `*.xlsx`, `uploads`, `logs`, `export`, `new-datas`, `---bak---`, archives, dumps, and test caches.

- [ ] **Step 4: Add Compose topology and environment template**

Create `compose.yaml`:

```yaml
name: student-analysis
services:
  db:
    image: mysql:8.4.2
    container_name: student-analysis-db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-student_analysis}
      MYSQL_USER: ${MYSQL_USER:-student_analysis}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}
      TZ: Asia/Shanghai
    command: ["--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci"]
    volumes:
      - db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD-SHELL", "mysqladmin ping -h 127.0.0.1 -uroot -p$$MYSQL_ROOT_PASSWORD --silent"]
      interval: 10s
      timeout: 5s
      retries: 12
    networks: [internal]
    mem_limit: 2g
    cpus: "1.5"
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "3"}

  web:
    build: .
    image: student-analysis:${RELEASE_VERSION:?RELEASE_VERSION is required}
    container_name: student-analysis-web
    restart: unless-stopped
    environment:
      FLASK_ENV: prod
      MYSQL_HOST: db
      MYSQL_PORT: 3306
      MYSQL_DATABASE: ${MYSQL_DATABASE:-student_analysis}
      MYSQL_USER: ${MYSQL_USER:-student_analysis}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?MYSQL_PASSWORD is required}
      SECRET_KEY: ${SECRET_KEY:?SECRET_KEY is required}
      UPLOAD_FOLDER: /app/uploads
      LOG_FOLDER: /app/logs
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    depends_on:
      db: {condition: service_healthy}
    volumes:
      - uploads:/app/uploads
      - app_logs:/app/logs
    networks: [internal, proxy]
    mem_limit: 1g
    cpus: "1.0"
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "3"}

networks:
  internal: {internal: true}
  proxy:
    name: ${PROXY_NETWORK:?PROXY_NETWORK is required}
    external: true

volumes:
  db_data: {name: student-analysis-db-data}
  uploads: {name: student-analysis-uploads}
  app_logs: {name: student-analysis-logs}
```

Create `.env.example` with non-secret examples and comments:

```dotenv
PROXY_NETWORK=reverse-proxy
PROXY_CONTAINER=reverse-proxy
MYSQL_DATABASE=student_analysis
MYSQL_USER=student_analysis
MYSQL_PASSWORD=change-me
MYSQL_ROOT_PASSWORD=change-me
SECRET_KEY=change-me
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=120
LOG_LEVEL=INFO
```

- [ ] **Step 5: Validate files and Compose interpolation**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: 3 tests PASS.

Run on Linux/WSL with safe temporary values:

```bash
cp .env.example .env
sed -i 's/=change-me/=verification-only-secret-1234567890/' .env
docker network inspect reverse-proxy >/dev/null 2>&1 || docker network create reverse-proxy
docker compose --env-file .env config --quiet
rm .env
```

Expected: `docker compose config --quiet` exits 0 and prints no validation error. Remove only the test `.env`; do not remove an existing user `.env`—perform this check in an isolated worktree.

- [ ] **Step 6: Commit Task 3 only**

```bash
git add requirements-prod.txt Dockerfile .dockerignore compose.yaml .env.example tests/test_deployment_assets.py
git commit -m "feat: add production container topology"
```

---

### Task 4: Release Installer, Shared Operations Library, and Deployment Orchestrator

**Files:**

- Create: `scripts/ops_common.sh`
- Create: `scripts/install_release.sh`
- Create: `scripts/deploy.sh`
- Modify: `tests/test_deployment_assets.py`

**Interfaces:**

- Produces: `load_env`, `require_command`, `require_safe_root`, `compose`, `wait_for_healthy`, and `atomic_current_link` shell functions.
- Produces: `scripts/install_release.sh ABSOLUTE_ARCHIVE_PATH`, which verifies the adjacent `.sha256`, safely extracts one version directory, and invokes its deploy script.
- Consumes: `/opt/student-analysis/shared/.env`, `compose.yaml`, `PROXY_NETWORK`, and `PROXY_CONTAINER`.
- Produces: `scripts/deploy.sh RELEASE_DIR`, returning nonzero at the first failed validation/deployment stage.

- [ ] **Step 1: Add failing script-policy tests**

Append to `tests/test_deployment_assets.py`:

```python
    def test_deploy_is_fail_fast_and_never_resets_database(self):
        deploy = self.read("scripts/deploy.sh")
        self.assertIn("set -Eeuo pipefail", deploy)
        self.assertIn("init_database.py --tables-only", deploy)
        self.assertNotIn("--reset", deploy)
        self.assertIn("PROXY_CONTAINER", deploy)

    def test_installer_verifies_checksum_before_extracting(self):
        installer = self.read("scripts/install_release.sh")
        self.assertLess(installer.index("sha256sum --check"), installer.index("tar -xzf"))
        self.assertIn("--no-same-owner", installer)

    def test_operations_library_restricts_server_root(self):
        common = self.read("scripts/ops_common.sh")
        self.assertIn('/opt/student-analysis', common)
        self.assertIn("docker compose", common)
```

- [ ] **Step 2: Run tests and confirm missing script failures**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: ERROR because the new operations scripts do not exist.

- [ ] **Step 3: Implement the common operations API**

Create `scripts/ops_common.sh` with `set -Eeuo pipefail` and these exact behaviors:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_ROOT="${APP_ROOT:-/opt/student-analysis}"
readonly SHARED_ENV="${SHARED_ENV:-${APP_ROOT}/shared/.env}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }
require_safe_root() {
  local resolved
  resolved="$(realpath -m "$APP_ROOT")"
  [[ "$resolved" == /opt/student-analysis ]] || die "Unsafe APP_ROOT: $resolved"
}
load_env() {
  [[ -f "$SHARED_ENV" ]] || die "Missing environment file: $SHARED_ENV"
  set -a
  source "$SHARED_ENV"
  set +a
  for key in PROXY_NETWORK PROXY_CONTAINER MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD MYSQL_ROOT_PASSWORD SECRET_KEY; do
    [[ -n "${!key:-}" && "${!key}" != change-me ]] || die "Unsafe or missing $key"
  done
}
compose() { docker compose --env-file "$SHARED_ENV" -f "$RELEASE_DIR/compose.yaml" "$@"; }
wait_for_healthy() {
  local container="$1" attempts="${2:-60}" status
  for ((i=1; i<=attempts; i++)); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    [[ "$status" == healthy ]] && return 0
    sleep 2
  done
  die "Container did not become healthy: $container"
}
atomic_current_link() {
  local target="$1" temporary="${APP_ROOT}/.current.new"
  ln -sfn "$target" "$temporary"
  mv -Tf "$temporary" "${APP_ROOT}/current"
}
```

- [ ] **Step 4: Implement checksum-first release installation**

Create `scripts/install_release.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/student-analysis}"
archive="$(realpath "${1:?Usage: install_release.sh ABSOLUTE_ARCHIVE_PATH}")"
checksum="${archive}.sha256"
[[ "$archive" == *.tar.gz ]] || { echo "Archive must end in .tar.gz" >&2; exit 2; }
[[ -f "$checksum" ]] || { echo "Missing checksum: $checksum" >&2; exit 2; }
(cd "$(dirname "$archive")" && sha256sum --check "$(basename "$checksum")")
filename="$(basename "$archive")"
version="${filename#student-analysis-release-}"
version="${version%.tar.gz}"
[[ "$version" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[0-9]+$ ]] || { echo "Invalid release version" >&2; exit 2; }
release_dir="${APP_ROOT}/releases/${version}"
[[ ! -e "$release_dir" ]] || { echo "Release already exists: $release_dir" >&2; exit 2; }
mkdir -p "$release_dir"
tar -xzf "$archive" --no-same-owner --no-same-permissions -C "$release_dir"
RELEASE_VERSION="$version" "$release_dir/scripts/deploy.sh"
```

The exporter must store files directly at the archive root, so extraction produces exactly one release directory controlled by this script. Run the installer as a server administrator; never accept a relative archive path.

- [ ] **Step 5: Implement fail-fast deployment with Web rollback**

Create `scripts/deploy.sh` that sources the library and executes this sequence:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
RELEASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export RELEASE_VERSION="${RELEASE_VERSION:-$(basename "$RELEASE_DIR")}"
source "$RELEASE_DIR/scripts/ops_common.sh"

trap 'printf "Deployment failed at line %s\n" "$LINENO" >&2' ERR
require_safe_root
require_command docker
load_env
docker compose version >/dev/null
docker network inspect "$PROXY_NETWORK" >/dev/null
docker inspect "$PROXY_CONTAINER" >/dev/null
mkdir -p "$APP_ROOT/releases" "$APP_ROOT/backups" "$APP_ROOT/shared"

previous_image="$(docker inspect --format '{{.Image}}' student-analysis-web 2>/dev/null || true)"
rollback_web() {
  local code="$?"
  trap - ERR
  printf 'Deployment failed; attempting Web rollback\n' >&2
  if [[ -n "$previous_image" ]]; then
    docker tag "$previous_image" "student-analysis:${RELEASE_VERSION}"
    compose up -d --no-deps --force-recreate web
    wait_for_healthy student-analysis-web 60 || true
  fi
  exit "$code"
}
trap rollback_web ERR

if docker inspect student-analysis-db >/dev/null 2>&1; then
  "$RELEASE_DIR/scripts/backup.sh" pre-deploy
fi

compose build --pull web
compose up -d db
wait_for_healthy student-analysis-db 60
compose run --rm web python init_database.py --tables-only
compose up -d web
wait_for_healthy student-analysis-web 60

docker exec "$PROXY_CONTAINER" sh -ec \
  "wget -qO- http://student-analysis-web:8000/health | grep -q '\"status\":\"ok\"'"
atomic_current_link "$RELEASE_DIR"
compose ps
printf 'Deployment complete. Proxy target: http://student-analysis-web:8000\n'
```

Document in a comment that the existing proxy container must contain `sh`, `wget`, and `grep`; if inspection shows the concrete proxy image lacks them, use its available HTTP client in this exact probe and update the static test to match. The rollback trap must never restore database content automatically.

- [ ] **Step 6: Run syntax and policy tests**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: all deployment-asset tests PASS.

Run on Linux/WSL: `bash -n scripts/ops_common.sh scripts/install_release.sh scripts/deploy.sh`

Expected: exit 0 with no output.

- [ ] **Step 7: Commit Task 4 only**

```bash
git add scripts/ops_common.sh scripts/install_release.sh scripts/deploy.sh tests/test_deployment_assets.py
git commit -m "feat: add fail-fast deployment orchestration"
```

---

### Task 5: Backup and Guarded Restore

**Files:**

- Create: `scripts/backup.sh`
- Create: `scripts/restore.sh`
- Modify: `tests/test_deployment_assets.py`

**Interfaces:**

- Produces: `scripts/backup.sh [label]`, writing a timestamped database dump, uploads archive, and SHA-256 manifest under `/opt/student-analysis/backups`.
- Produces: `scripts/restore.sh ABSOLUTE_BACKUP_DIRECTORY`, accepting only a verified directory below `/opt/student-analysis/backups` and the exact confirmation text `RESTORE student_analysis`.

- [ ] **Step 1: Add failing backup/restore safety tests**

Append:

```python
    def test_restore_requires_safe_path_checksum_and_confirmation(self):
        restore = self.read("scripts/restore.sh")
        self.assertIn("require_safe_backup_path", restore)
        self.assertIn("sha256sum --check", restore)
        self.assertIn("RESTORE student_analysis", restore)
        self.assertNotIn("DROP DATABASE", restore)

    def test_backup_creates_database_uploads_and_manifest(self):
        backup = self.read("scripts/backup.sh")
        self.assertIn("mysqldump", backup)
        self.assertIn("uploads.tar.gz", backup)
        self.assertIn("SHA256SUMS", backup)
```

- [ ] **Step 2: Run tests and confirm missing-file failures**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: ERROR for missing backup and restore scripts.

- [ ] **Step 3: Implement timestamped backup**

Create `scripts/backup.sh` with this setup before the backup commands so it also works from cron:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/student-analysis}"
RELEASE_DIR="$(readlink -f "${APP_ROOT}/current")"
export RELEASE_VERSION="$(basename "$RELEASE_DIR")"
source "$RELEASE_DIR/scripts/ops_common.sh"
require_safe_root
load_env
label="${1:-manual}"
[[ "$label" =~ ^[A-Za-z0-9._-]+$ ]] || die "Invalid backup label"
timestamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="${APP_ROOT}/backups/${timestamp}-${label}"
install -d -m 700 "$backup_dir"
```

Then execute:

```bash
compose exec -T db sh -ec \
  'exec mysqldump --single-transaction --routines --triggers -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > "$backup_dir/database.sql"
docker run --rm \
  -v student-analysis-uploads:/data:ro \
  -v "$backup_dir":/backup \
  alpine:3.20.3 tar -C /data -czf /backup/uploads.tar.gz .
(cd "$backup_dir" && sha256sum database.sql uploads.tar.gz > SHA256SUMS)
chmod 600 "$backup_dir/database.sql" "$backup_dir/uploads.tar.gz" "$backup_dir/SHA256SUMS"
```

Validate `label` against `^[A-Za-z0-9._-]+$`; fail if the SQL dump is empty. Print the absolute backup directory on success. Retention cleanup is documented for cron and is not performed during deployment.

- [ ] **Step 4: Implement explicit, verified restore**

Create `scripts/restore.sh` with:

```bash
require_safe_backup_path() {
  local candidate
  candidate="$(realpath "$1")"
  [[ "$candidate" == "${APP_ROOT}/backups/"* ]] || die "Backup path is outside APP_ROOT"
  [[ -f "$candidate/SHA256SUMS" ]] || die "Missing SHA256SUMS"
  printf '%s\n' "$candidate"
}
```

Implement the restore body with exact confirmation and no database deletion:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
APP_ROOT="${APP_ROOT:-/opt/student-analysis}"
RELEASE_DIR="$(readlink -f "${APP_ROOT}/current")"
export RELEASE_VERSION="$(basename "$RELEASE_DIR")"
source "$RELEASE_DIR/scripts/ops_common.sh"
require_safe_root
load_env
backup_dir="$(require_safe_backup_path "${1:?Usage: restore.sh ABSOLUTE_BACKUP_DIRECTORY}")"
(cd "$backup_dir" && sha256sum --check SHA256SUMS)
read -r -p "Type RESTORE student_analysis to continue: " confirmation
[[ "$confirmation" == "RESTORE student_analysis" ]] || die "Restore cancelled"

compose stop web
compose exec -T db sh -ec \
  'exec mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < "$backup_dir/database.sql"

safety="pre-restore-$(date +%Y%m%d_%H%M%S)"
docker run --rm \
  -v student-analysis-uploads:/data \
  -v "$backup_dir":/backup:ro \
  alpine:3.20.3 sh -ec \
  "mkdir -p /data/$safety && find /data -mindepth 1 -maxdepth 1 ! -name '$safety' -exec mv {} /data/$safety/ \\; && tar -C /data -xzf /backup/uploads.tar.gz"

compose up -d web
wait_for_healthy student-analysis-web 60
printf 'Restore complete; verify imports, dashboard, student, knowledge, and warning pages.\n'
```

Do not include `DROP DATABASE`, `docker compose down -v`, or volume deletion.

- [ ] **Step 5: Run syntax and safety tests**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: all tests PASS.

Run on Linux/WSL: `bash -n scripts/backup.sh scripts/restore.sh`

Expected: exit 0.

- [ ] **Step 6: Commit Task 5 only**

```bash
git add scripts/backup.sh scripts/restore.sh tests/test_deployment_assets.py
git commit -m "feat: add verified backup and restore tools"
```

---

### Task 6: Allowlist Release Exporter and Platform Wrappers

**Files:**

- Create: `scripts/export_release.py`
- Create: `tests/test_release_export.py`
- Modify: `export.sh`
- Modify: `export.bat`
- Modify: `.gitignore`

**Interfaces:**

- Produces: `collect_release_files(root: Path) -> list[Path]`.
- Produces: `build_release(root: Path, output_dir: Path, version: str) -> tuple[Path, Path]`.
- Produces: `python scripts/export_release.py --version 2026.07.20-1 --output export`.

- [ ] **Step 1: Write failing exporter tests**

```python
# tests/test_release_export.py
import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.export_release import build_release, collect_release_files


class ReleaseExportTest(unittest.TestCase):
    def test_allowlist_excludes_student_data_and_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "controllers").mkdir()
            (root / "controllers" / "ok.py").write_text("pass\n", encoding="utf-8")
            (root / "controllers" / "student.xlsx").write_bytes(b"private")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("secret", encoding="utf-8")
            (root / "app.py").write_text("pass\n", encoding="utf-8")
            names = {path.relative_to(root).as_posix() for path in collect_release_files(root)}
        self.assertEqual(names, {"app.py", "controllers/ok.py"})

    def test_build_writes_archive_and_matching_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            output = Path(tmp) / "out"
            root.mkdir()
            (root / "app.py").write_text("pass\n", encoding="utf-8")
            archive, checksum = build_release(root, output, "2026.07.20-1")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text().split()[0], digest)
            with tarfile.open(archive, "r:gz") as package:
                self.assertEqual(package.getnames(), ["app.py"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and confirm missing-module failure**

Run: `python -m unittest tests.test_release_export -v`

Expected: ERROR with `ModuleNotFoundError: scripts.export_release`.

- [ ] **Step 3: Implement strict allowlist packaging**

Implement `scripts/export_release.py` with:

```python
ALLOWED_ROOT_FILES = {
    ".dockerignore", ".env.example", "app.py", "compose.yaml", "config.py",
    "DEPLOY.md", "Dockerfile", "init_database.py", "requirements-prod.txt", "wsgi.py",
}
ALLOWED_DIRECTORIES = {
    "config", "controllers", "models", "repositories", "scripts", "services", "static", "templates",
}
FORBIDDEN_SUFFIXES = {
    ".7z", ".dump", ".gz", ".key", ".log", ".pyc", ".rar", ".sql", ".xls", ".xlsx", ".zip",
}
FORBIDDEN_PARTS = {".git", ".agents", "__pycache__", "uploads", "logs", "export", "new-datas", "---bak---"}


def collect_release_files(root: Path) -> list[Path]:
    candidates = [root / name for name in ALLOWED_ROOT_FILES]
    for directory in sorted(ALLOWED_DIRECTORIES):
        base = root / directory
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if path.is_file())
    selected = []
    for path in candidates:
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name == ".env":
            continue
        selected.append(path)
    return sorted(set(selected), key=lambda item: item.relative_to(root).as_posix())
```

`build_release` must validate version with `^[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[0-9]+$`, use `tarfile` with relative POSIX names, set member metadata (`uid=gid=0`, empty owner/group, `mtime=0`), write via a temporary filename, atomically replace the final archive, and write `<archive>.sha256` as `<digest>  <filename>\n`. Add `validate_project_root(root)` for the CLI path; it requires every `ALLOWED_ROOT_FILES` entry before calling `build_release`. Unit tests call `build_release` directly with their minimal fixture.

- [ ] **Step 4: Replace legacy wrappers and update ignore rules**

`export.sh`:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
version="${1:-$(date +%Y.%m.%d)-1}"
exec python3 scripts/export_release.py --version "$version" --output export
```

`export.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: export.bat YYYY.MM.DD-N
  exit /b 2
)
python scripts\export_release.py --version "%~1" --output export
exit /b %ERRORLEVEL%
```

Ensure `.gitignore` contains `.env`, `export/`, `*.tar.gz`, `*.sha256`, `uploads/`, `logs/`, and spreadsheet rules for deployment data while preserving `.env.example` via `!.env.example`.

- [ ] **Step 5: Run exporter tests and inspect a real release**

Run: `python -m unittest tests.test_release_export -v`

Expected: 2 tests PASS.

Run: `python scripts/export_release.py --version 2026.07.20-1 --output export`

Expected: creates `export/student-analysis-release-2026.07.20-1.tar.gz` and matching `.sha256`.

Run on Linux/WSL:

```bash
tar -tzf export/student-analysis-release-2026.07.20-1.tar.gz | grep -E '(^|/)(\.git|\.env|uploads|logs|new-datas|---bak---)(/|$)|\.(xls|xlsx|sql|log)$' && exit 1 || true
sha256sum --check export/student-analysis-release-2026.07.20-1.tar.gz.sha256
```

Expected: privacy grep prints nothing; checksum prints `OK`.

- [ ] **Step 6: Commit Task 6 only**

```bash
git add scripts/export_release.py tests/test_release_export.py export.sh export.bat .gitignore
git commit -m "feat: create privacy-safe release archives"
```

---

### Task 7: Deployment Runbook and End-to-End Verification

**Files:**

- Create: `DEPLOY.md`
- Modify: `README.md`
- Modify: `tests/test_deployment_assets.py`

**Interfaces:**

- Consumes: all commands, environment variables, container names, paths, scripts, and health behavior defined in Tasks 1–6.
- Produces: one operator runbook for first deployment, proxy setup, upgrade, rollback, backup, restore, scheduled retention, diagnostics, and acceptance.

- [ ] **Step 1: Add failing runbook coverage test**

Append:

```python
    def test_runbook_covers_required_operations(self):
        runbook = self.read("DEPLOY.md")
        for phrase in (
            "国内镜像源",
            "student-analysis-web:8000",
            "首次部署",
            "升级",
            "回滚",
            "备份",
            "恢复",
            "/health",
            "校园网",
        ):
            self.assertIn(phrase, runbook)
```

- [ ] **Step 2: Run test and confirm missing runbook failure**

Run: `python -m unittest tests.test_deployment_assets -v`

Expected: ERROR because `DEPLOY.md` does not exist.

- [ ] **Step 3: Write the operator runbook**

Write `DEPLOY.md` with exact commands for:

1. Configuring a domestic Docker registry mirror and verifying `docker pull python:3.11.9-slim-bookworm` and `docker pull mysql:8.4.2`.
2. Creating `/opt/student-analysis/{releases,shared,backups}` with administrator-only permissions.
3. Generating `SECRET_KEY` using `openssl rand -hex 32`, generating two distinct database passwords, and setting `PROXY_NETWORK`/`PROXY_CONTAINER`.
4. Inspecting the existing proxy network with `docker network inspect "$PROXY_NETWORK"`.
5. Uploading archive and checksum. On the first deployment, run `sha256sum --check` manually before extracting into `/opt/student-analysis/releases/2026.07.20-1` and invoking `scripts/deploy.sh`. On later upgrades, run the already trusted `/opt/student-analysis/current/scripts/install_release.sh /absolute/path/student-analysis-release-2026.08.01-1.tar.gz`, which verifies before extraction.
6. Adding the existing proxy target `http://student-analysis-web:8000` without publishing a host port.
7. Running every acceptance check from the design spec.
8. Upgrading with a new version directory and reading the pre-deployment backup path.
9. Rolling the Web image back to the previous release without deleting volumes.
10. Scheduling `scripts/backup.sh daily` and a path-validated retention command for 7 daily and 4 weekly backups.
11. Performing restore first in an isolated Compose project/volume set, then using production restore only with an approved maintenance window.
12. Diagnosing with `docker compose ps`, `docker inspect`, `docker compose logs --tail=200`, `docker system df`, and `docker volume inspect`.

Update the deployment section of `README.md` to point to `DEPLOY.md` and remove instructions that present the Flask development server or old ZIP exporter as production deployment.

- [ ] **Step 4: Run the complete automated suite**

Run:

```bash
python -m unittest tests.test_production_runtime tests.test_health tests.test_deployment_assets tests.test_release_export -v
python test_column_mapping.py
bash -n scripts/ops_common.sh scripts/install_release.sh scripts/deploy.sh scripts/backup.sh scripts/restore.sh export.sh
```

Expected: all unit tests PASS, column-mapping test exits 0, and every shell file passes syntax validation.

- [ ] **Step 5: Run isolated container acceptance**

In an isolated Linux/WSL worktree, create a temporary external proxy network and temporary proxy container, populate `.env` with verification-only secrets, then run:

```bash
docker network create student-analysis-verification-proxy
docker run -d --name student-analysis-verification-proxy --network student-analysis-verification-proxy alpine:3.20.3 sleep 1d
docker compose --env-file .env build web
docker compose --env-file .env up -d db
docker compose --env-file .env run --rm web python init_database.py --tables-only
docker compose --env-file .env up -d web
docker compose --env-file .env ps
docker exec student-analysis-verification-proxy wget -qO- http://student-analysis-web:8000/health
```

Expected: both project containers report healthy; proxy probe returns `{"status":"ok"}`; `docker port student-analysis-web` and `docker port student-analysis-db` print nothing.

After recording evidence, clean up only the explicitly named verification containers/network/volumes from the isolated environment. Resolve and verify their exact names before deletion; do not use broad Docker prune commands.

- [ ] **Step 6: Build and inspect the final release artifact**

Run:

```bash
python scripts/export_release.py --version 2026.07.20-1 --output export
sha256sum --check export/student-analysis-release-2026.07.20-1.tar.gz.sha256
tar -tzf export/student-analysis-release-2026.07.20-1.tar.gz
```

Expected: checksum is `OK`; archive contains only source/runtime/deployment files and no student data, `.git`, `.env`, logs, uploads, dumps, or earlier archives.

- [ ] **Step 7: Commit documentation and verification updates**

```bash
git add DEPLOY.md README.md tests/test_deployment_assets.py
git commit -m "docs: add deployment and recovery runbook"
```

---

## Final Review Gate

- [ ] Confirm `git diff --check` reports no whitespace errors.
- [ ] Confirm the complete automated suite and isolated Compose acceptance outputs are captured.
- [ ] Confirm the final archive privacy scan and SHA-256 verification pass.
- [ ] Confirm only files listed in this plan are included in deployment commits; preserve the user's unrelated modifications.
- [ ] Invoke `superpowers:verification-before-completion` before claiming the deployment package is ready.
- [ ] Invoke `superpowers:requesting-code-review` for an independent review of configuration safety, Compose networking, destructive-operation guards, and release privacy.
