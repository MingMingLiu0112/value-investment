"""Shared fixtures for the local workbench API tests (WEB-D2 P0.1).

The private API is authorized, so every helper here performs the same
handshake the browser workbench performs: mint a session token from
`GET /api/v1/private/session` and present it on private reads and writes.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import create_app

TEST_PORT = 8791
TEST_HOST = "127.0.0.1:{port}"
SESSION_PATH = "/api/v1/private/session"


def operator_headers(
    port: int = TEST_PORT,
    *,
    token: str | None = None,
    origin: str | None = None,
) -> dict[str, str]:
    headers = {"host": TEST_HOST.format(port=port)}
    headers["origin"] = origin if origin is not None else f"http://127.0.0.1:{port}"
    if token is not None:
        headers["x-local-session"] = token
    return headers


def open_session(client: TestClient) -> str:
    response = client.get(SESSION_PATH, headers=operator_headers())
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["action"] == "no_order"
    return payload["token"]


def operator_client(app: FastAPI) -> TestClient:
    client = TestClient(app, base_url=f"http://127.0.0.1:{TEST_PORT}",
                        client=("127.0.0.1", 51000))
    client.headers.update(operator_headers())
    client.headers["x-local-session"] = open_session(client)
    return client


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    # The guard requires the private root outside every Git worktree, so it cannot
    # live under pytest's temporary directory when that sits inside the repository.
    private = Path(tempfile.mkdtemp(prefix="vi-api-private-", dir=Path.home()))
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(private))
    try:
        yield project, private
    finally:
        shutil.rmtree(private, ignore_errors=True)


@pytest.fixture()
def make_client(workspace):
    project, _ = workspace

    def build(
        *,
        authorize: bool = True,
        port: int = TEST_PORT,
        session_ttl_seconds: float = 12 * 60 * 60.0,
        base_url: str | None = None,
        client_address: tuple[str, int] = ("127.0.0.1", 51000),
    ) -> TestClient:
        app = create_app(project, port=port, session_ttl_seconds=session_ttl_seconds)
        client = TestClient(app, base_url=base_url or f"http://127.0.0.1:{port}",
                            client=client_address)
        if authorize:
            client.headers.update(operator_headers(port))
            client.headers["x-local-session"] = open_session(client)
        return client

    return build


@pytest.fixture()
def client(make_client):
    return make_client()


@pytest.fixture()
def workbench_origin():
    return f"http://127.0.0.1:{TEST_PORT}"
