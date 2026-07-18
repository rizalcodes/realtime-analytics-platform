"""Tests for the auth primitives in api/auth.py."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from jose import JWTError

from api.auth import (
    create_access_token,
    hash_password,
    verify_password,
    verify_token,
)


def test_password_hash_round_trip():
    hashed = hash_password("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)
    assert not verify_password("wrong-pass", hashed)


def test_valid_token_verifies_with_payload():
    token = create_access_token({"sub": "user@example.com", "role": "viewer"})
    payload = verify_token(token)
    assert payload["sub"] == "user@example.com"
    assert payload["role"] == "viewer"
    assert "exp" in payload


def test_tampered_token_fails_verification():
    token = create_access_token({"sub": "user@example.com", "role": "viewer"})
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(JWTError):
        verify_token(tampered)


def test_garbage_token_fails_verification():
    with pytest.raises(JWTError):
        verify_token("not.a.jwt")
