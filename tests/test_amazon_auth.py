"""
Tests for src.amazon.auth

Mocks requests.post -- there's no real Amazon developer app registered
yet, so these test the token-exchange logic (request shape, error
handling) without ever making a real network call.
"""

from unittest.mock import Mock, patch

import pytest

from src.amazon.auth import LwaAuthError, get_access_token


def test_get_access_token_returns_token_on_success():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"access_token": "Atza|fake-token", "expires_in": 3600}

    with patch("src.amazon.auth.requests.post", return_value=fake_response) as mock_post:
        token = get_access_token("client-id", "client-secret", "refresh-token")

    assert token == "Atza|fake-token"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["data"]["grant_type"] == "refresh_token"
    assert call_kwargs["data"]["client_id"] == "client-id"
    assert call_kwargs["data"]["refresh_token"] == "refresh-token"


def test_get_access_token_raises_on_non_200_response():
    fake_response = Mock()
    fake_response.status_code = 400
    fake_response.text = '{"error": "invalid_grant"}'

    with patch("src.amazon.auth.requests.post", return_value=fake_response):
        with pytest.raises(LwaAuthError, match="400"):
            get_access_token("client-id", "client-secret", "bad-refresh-token")


def test_get_access_token_raises_if_credentials_are_missing():
    with pytest.raises(LwaAuthError, match="incomplete"):
        get_access_token("", "client-secret", "refresh-token")


def test_get_access_token_raises_if_response_has_no_access_token():
    fake_response = Mock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"unexpected": "shape"}

    with patch("src.amazon.auth.requests.post", return_value=fake_response):
        with pytest.raises(LwaAuthError, match="did not include"):
            get_access_token("client-id", "client-secret", "refresh-token")