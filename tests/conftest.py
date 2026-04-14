import importlib
import os
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client(monkeypatch):
    # Ensure the project root is on sys.path so tests can import application modules
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    # Import application only after ensuring sys.path contains project root
    main = importlib.import_module("main")

    # Prevent tests from modifying the real database when importing startup hooks
    monkeypatch.setattr(main, "create_db_and_tables", lambda: None)
    with TestClient(main.app) as test_client:
        yield test_client
