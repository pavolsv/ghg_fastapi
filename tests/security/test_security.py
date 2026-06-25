"""
Common security tests for the FastAPI application.

These tests check for OWASP-style issues without needing a running server:
- Hard-coded secrets in source code
- Security headers on HTTP responses
- Path traversal via file uploads
- SQL injection / XSS payloads on public forms
- Plain-text password storage patterns
"""

import os
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIRS = [PROJECT_ROOT / "routers", PROJECT_ROOT]
SOURCE_PATTERNS = ["*.py"]

SECRET_PATTERNS = [
    re.compile(r"secret_key\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"SECRET_KEY\s*=\s*['\"][^'\"]+['\"]"),
    re.compile(r"api_key\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", re.IGNORECASE),
    re.compile(r"password\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
]

# False positives: unit-test fixtures, docs, env example files
EXCLUDED_FILES = {
    "test_security.py",
    "conftest.py",
    "test_health.py",
    ".env.example",
}


def _iter_source_files():
    for directory in SOURCE_DIRS:
        if not directory.exists():
            continue
        for pattern in SOURCE_PATTERNS:
            for path in directory.rglob(pattern):
                if path.name in EXCLUDED_FILES:
                    continue
                if any(part in {"venv", ".venv", "__pycache__", "uploads"} for part in path.parts):
                    continue
                yield path


def test_no_hardcoded_secrets_in_source():
    """Fail if obvious hard-coded secrets are present in Python source."""
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path}:{line_no}: {match.group()[:80]}")
    assert not offenders, "Hard-coded secrets detected:\n" + "\n".join(offenders)


def test_main_uses_env_for_session_secret():
    """The session secret key should be loaded from environment, not hard-coded."""
    main_path = PROJECT_ROOT / "main.py"
    text = main_path.read_text(encoding="utf-8")
    assert "os.environ.get(\"SESSION_SECRET_KEY\")" in text, (
        "main.py should read SESSION_SECRET_KEY from the environment"
    )


def test_security_headers_on_root(client):
    """Basic security headers should be present on HTML responses."""
    response = client.get("/")
    assert response.status_code == 200
    headers = {k.lower(): v for k, v in response.headers.items()}
    # FastAPI/Starlette sets content-type; ensure HTML is served
    assert "text/html" in headers.get("content-type", "")
    # Frame options help prevent clickjacking
    assert headers.get("x-frame-options", "").upper() in ("DENY", "SAMEORIGIN")


def test_sql_injection_payload_on_login(client):
    """Login endpoint should not authenticate using a SQL-injection payload."""
    payload = {
        "username": "admin' OR '1'='1",
        "password": "admin' OR '1'='1",
        "VerificationCode": "",
    }
    response = client.post("/login/", data=payload, follow_redirects=False)
    assert response.status_code in (200, 302, 303)
    # It should not redirect to the authenticated index page
    if response.status_code in (302, 303):
        assert response.headers.get("location") != "/index/"


def test_xss_payload_reflected_on_login(client):
    """Login form should not reflect a script payload unsanitised."""
    xss_payload = "<script>alert('xss')</script>"
    payload = {
        "username": xss_payload,
        "password": "anything",
        "VerificationCode": "",
    }
    response = client.post("/login/", data=payload)
    assert response.status_code == 200
    # If the username is echoed back, it should be escaped
    assert xss_payload not in response.text


def test_path_traversal_upload_attempt(client):
    """Upload endpoints should reject or sanitise path traversal in filenames."""
    traversal_name = "../../../outside_uploads/evil.png"
    response = client.post(
        "/upload",
        files={"imageFile": (traversal_name, b"fake image bytes", "image/png")},
    )
    # The endpoint may return 200 (OCR failure) or 500, but must not create a
    # file outside the intended uploads directory.
    assert not (PROJECT_ROOT / "outside_uploads" / "evil.png").exists()
    # Ensure no file was created at the project root either
    assert not (PROJECT_ROOT / traversal_name).exists()


def test_password_storage_uses_hashing():
    """Passwords should not be stored or compared in plain text."""
    login_path = PROJECT_ROOT / "routers" / "login.py"
    register_path = PROJECT_ROOT / "routers" / "register.py"

    login_text = login_path.read_text(encoding="utf-8")
    register_text = register_path.read_text(encoding="utf-8")

    # Reject direct equality comparison with stored password column
    assert "Account.password == password" not in login_text, (
        "Login compares plain-text passwords; use a password hashing library"
    )

    # Reject assignment of raw password to model field
    assert "Account(account=username, email=email, password=password)" not in register_text, (
        "Register stores plain-text passwords; hash them before saving"
    )


def test_session_cookie_has_security_attributes(client):
    """Session cookies should be HttpOnly to mitigate XSS cookie theft."""
    response = client.get("/")
    set_cookie = response.headers.get("set-cookie", "")
    if set_cookie:
        assert "httponly" in set_cookie.lower(), "Session cookie must be HttpOnly"


def test_open_redirect_not_allowed_on_login(client):
    """Login redirect target should be a fixed local path."""
    response = client.post(
        "/login/",
        data={
            "username": "admin",
            "password": "admin",
            "VerificationCode": "",
        },
        follow_redirects=False,
    )
    if response.status_code in (302, 303):
        location = response.headers.get("location", "")
        assert not location.startswith("http://") and not location.startswith("https://"), (
            "Open redirect to external host detected"
        )
