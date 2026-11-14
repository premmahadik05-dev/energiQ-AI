"""Fixtures for API integration tests: a real FastAPI app, a real database, real jobs (run inline).

The plain helper functions are in itest_support.py (see its docstring for why they are not in this file).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from itest_support import make_settings

from backend.app.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(make_settings(tmp_path))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
