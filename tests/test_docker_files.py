"""Tests for Docker deployment files (PO-012)."""

from __future__ import annotations

import os

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _repo_file(name: str) -> str:
    return os.path.join(REPO_ROOT, name)


def _read(name: str) -> str:
    with open(_repo_file(name)) as fh:
        return fh.read()


# ── Dockerfile ──────────────────────────────────────────────────────────────────


def test_dockerfile_exists() -> None:
    assert os.path.exists(_repo_file("Dockerfile")), "Dockerfile not found at repo root"


def test_dockerfile_uses_slim() -> None:
    content = _read("Dockerfile")
    assert "python:3.12-slim" in content


def test_dockerfile_has_nonroot_user() -> None:
    content = _read("Dockerfile")
    assert "appuser" in content


def test_dockerfile_multistage() -> None:
    content = _read("Dockerfile")
    assert "AS builder" in content
    assert "AS runtime" in content


def test_dockerfile_exposes_8000() -> None:
    content = _read("Dockerfile")
    assert "EXPOSE 8000" in content


def test_dockerfile_uvicorn_cmd() -> None:
    content = _read("Dockerfile")
    assert "uvicorn" in content
    assert "openorbit.main:app" in content


# ── docker-compose.yml ──────────────────────────────────────────────────────────


def test_docker_compose_exists() -> None:
    assert os.path.exists(_repo_file("docker-compose.yml"))


def test_docker_compose_valid_yaml() -> None:
    content = _read("docker-compose.yml")
    data = yaml.safe_load(content)
    assert data is not None
    assert "services" in data


def test_docker_compose_api_service() -> None:
    content = _read("docker-compose.yml")
    data = yaml.safe_load(content)
    assert "api" in data["services"]


def test_docker_compose_port_8000() -> None:
    content = _read("docker-compose.yml")
    data = yaml.safe_load(content)
    ports = data["services"]["api"].get("ports", [])
    assert any("8000" in str(p) for p in ports)


def test_docker_compose_data_volume() -> None:
    content = _read("docker-compose.yml")
    data = yaml.safe_load(content)
    volumes = data["services"]["api"].get("volumes", [])
    assert any("data" in str(v) for v in volumes)


# ── .dockerignore ───────────────────────────────────────────────────────────────


def test_dockerignore_exists() -> None:
    assert os.path.exists(_repo_file(".dockerignore"))


def test_dockerignore_excludes_state() -> None:
    content = _read(".dockerignore")
    assert "_fleet/" in content


def test_dockerignore_excludes_git() -> None:
    content = _read(".dockerignore")
    assert ".git/" in content


def test_dockerignore_excludes_pycache() -> None:
    content = _read(".dockerignore")
    assert "__pycache__/" in content


def test_dockerignore_excludes_tests() -> None:
    content = _read(".dockerignore")
    assert "tests/" in content


# ── docs/deployment.md ──────────────────────────────────────────────────────────


def test_deployment_docs_exist() -> None:
    assert os.path.exists(_repo_file("docs/deployment.md"))


def test_deployment_docs_has_build_command() -> None:
    content = _read("docs/deployment.md")
    assert "docker build" in content


def test_deployment_docs_has_compose_commands() -> None:
    content = _read("docs/deployment.md")
    assert "docker compose" in content


def test_deployment_docs_has_run_command() -> None:
    content = _read("docs/deployment.md")
    assert "docker run" in content
