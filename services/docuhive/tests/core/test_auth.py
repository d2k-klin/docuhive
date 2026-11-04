"""Password, request and login throttling behavior without a database."""

import pytest
from docuhive.auth import check_csrf, hash_password, token_hash, verify_password
from docuhive.auth.rate_limit import LoginLimiter
from fastapi import HTTPException
from starlette.requests import Request


def test_password_and_hash():
    with pytest.raises(ValueError):
        hash_password("short")
    stored = hash_password("a long synthetic password")
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, "a long synthetic password")
    assert not verify_password(stored, "incorrect")
    assert not verify_password("!disabled", "a long synthetic password")
    assert token_hash("raw") != "raw" and len(token_hash("raw")) == 64


@pytest.mark.parametrize("username", ["", "..", "a/b", "a\\b", "a\x00b", "a b"])
def test_usernames_cannot_be_paths(username):
    from docuhive.auth import create_user

    with pytest.raises(ValueError):
        create_user(username, "a valid synthetic password")


def test_csrf_is_required_for_mutations():
    with pytest.raises(HTTPException) as error:
        check_csrf(Request({"type": "http", "method": "POST", "headers": []}))
    assert error.value.status_code == 403
    check_csrf(Request({"type": "http", "method": "GET", "headers": []}))
    check_csrf(Request({"type": "http", "method": "POST", "headers": [(b"x-docuhive-csrf", b"1")]}))


def test_login_username_and_ip_limits_expire(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("docuhive.auth.rate_limit.time.monotonic", lambda: now[0])
    limiter = LoginLimiter()
    for _ in range(5):
        assert limiter.allowed("sample", "ip1")
        limiter.failed("sample", "ip1")
    assert not limiter.allowed("sample", "ip2")
    for index in range(15):
        limiter.failed(f"other{index}", "ip1")
    assert not limiter.allowed("new", "ip1")
    now[0] += 901
    assert limiter.allowed("sample", "ip1")
    assert not limiter.failures
