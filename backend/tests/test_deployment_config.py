from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_private_onlyoffice_stack() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = compose["services"]

    assert set(services) == {"postgres", "onlyoffice", "backend", "web"}
    assert services["onlyoffice"]["image"] == "onlyoffice/documentserver:9.4.0.1"
    assert "ports" not in services["onlyoffice"]
    assert services["onlyoffice"]["environment"]["ALLOW_PRIVATE_IP_ADDRESS"] == "true"
    assert services["onlyoffice"]["healthcheck"]
    assert services["backend"]["depends_on"]["onlyoffice"]["condition"] == "service_healthy"
    assert services["backend"]["environment"]["ONLYOFFICE_API_URL"] == "http://backend:8000"


def test_nginx_proxies_api_and_onlyoffice_virtual_path() -> None:
    config = (ROOT / "deploy" / "nginx.conf").read_text()

    assert "location /api/" in config
    assert "proxy_pass http://backend:8000;" in config
    assert "location /onlyoffice/" in config
    assert "proxy_pass http://onlyoffice/;" in config
    assert "proxy_set_header Upgrade $http_upgrade;" in config
    assert "proxy_set_header Connection $connection_upgrade;" in config
    assert "proxy_set_header X-Forwarded-Host $http_host/onlyoffice;" in config
    assert "proxy_set_header X-Forwarded-Proto $forwarded_proto;" in config
    assert "try_files $uri $uri/ /index.html;" in config


def test_container_builds_use_locked_dependencies_and_migrations() -> None:
    backend = (ROOT / "backend" / "Dockerfile").read_text()
    frontend = (ROOT / "frontend" / "Dockerfile").read_text()

    assert "uv sync --frozen" in backend
    assert "alembic upgrade head" in backend
    assert "exec uv run uvicorn" in backend
    assert "USER app" in backend
    assert "pnpm install --frozen-lockfile" in frontend
    assert "pnpm build" in frontend


def test_backup_script_is_fail_fast_and_does_not_embed_passwords() -> None:
    script = (ROOT / "deploy" / "backup-postgres.sh").read_text()

    assert "set -Eeuo pipefail" in script
    assert "mktemp" in script
    assert "trap cleanup EXIT" in script
    assert "pg_dump" in script
    assert "gzip" in script
    assert "gcloud storage cp" in script
    assert 'gs://*' in script
    assert "POSTGRES_PASSWORD" not in script


def test_example_environment_and_make_targets_are_documented() -> None:
    env_example = (ROOT / ".env.example").read_text()
    makefile = (ROOT / "Makefile").read_text()
    readme = (ROOT / "README.md").read_text()

    for name in (
        "POSTGRES_PASSWORD",
        "ONLYOFFICE_JWT_SECRET",
        "ONLYOFFICE_PUBLIC_URL",
        "GCP_PROJECT_ID",
        "GCS_BUCKET",
        "BACKUP_GCS_URI",
        "STORAGE_PROVIDER",
    ):
        assert f"{name}=" in env_example

    for target in ("stack-up:", "stack-down:", "stack-logs:", "migrate:"):
        assert target in makefile

    assert "systemd" in readme
    assert "restore" in readme.lower()
