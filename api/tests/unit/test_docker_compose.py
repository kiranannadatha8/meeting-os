"""Smoke-test the docker-compose.yml shape.

The acceptance criterion for T24 is "fresh clone → `docker compose up` →
app usable at localhost:3000". Parsing the YAML and asserting the five
services exist is a cheap regression guard — a dropped `worker` service
or a missing `depends_on` would silently break the 60s boot promise.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _load_compose() -> dict:
    with COMPOSE_PATH.open() as f:
        return yaml.safe_load(f)


def test_compose_declares_all_services() -> None:
    compose = _load_compose()
    assert set(compose["services"]) >= {"postgres", "redis", "api", "worker", "web"}


def test_api_and_worker_depend_on_infra() -> None:
    compose = _load_compose()
    for svc in ("api", "worker"):
        deps = compose["services"][svc].get("depends_on", {})
        assert "postgres" in deps, f"{svc} must depend on postgres"
        assert "redis" in deps, f"{svc} must depend on redis"


def test_web_depends_on_api() -> None:
    compose = _load_compose()
    deps = compose["services"]["web"].get("depends_on", {})
    assert "api" in deps


def test_api_exposes_port_8000_and_web_exposes_3000() -> None:
    compose = _load_compose()
    api_ports = compose["services"]["api"].get("ports", [])
    web_ports = compose["services"]["web"].get("ports", [])
    assert any("8000" in str(p) for p in api_ports)
    assert any("3000" in str(p) for p in web_ports)


def test_dockerfiles_exist() -> None:
    assert (REPO_ROOT / "api" / "Dockerfile").exists()
    assert (REPO_ROOT / "web" / "Dockerfile").exists()
