"""
Login with Amazon (LWA) authentication for SP-API.

As of October 2023, SP-API no longer requires AWS IAM credentials or
AWS Signature Version 4 signing -- every request just needs a bearer
access token obtained here, sent in the x-amz-access-token header.
This module's only job is that token exchange.
"""

import requests

from src.amazon.schema import LWA_TOKEN_URL


class LwaAuthError(Exception):
    """Raised when Amazon rejects the LWA token request (bad credentials, expired refresh token, etc.)."""


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """
    Exchange a long-lived LWA refresh token for a short-lived (1 hour)
    access token. Every SP-API call in this project should request a
    fresh token via this function rather than trying to cache/reuse
    one across runs -- a daily job doesn't run often enough for token
    caching to be worth the added complexity and staleness risk.
    """
    if not client_id or not client_secret or not refresh_token:
        raise LwaAuthError(
            "Amazon LWA credentials are incomplete. Check AMAZON_LWA_CLIENT_ID, "
            "AMAZON_LWA_CLIENT_SECRET, and AMAZON_REFRESH_TOKEN in .env."
        )

    response = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise LwaAuthError(
            f"LWA token request failed with status {response.status_code}: {response.text}"
        )

    body = response.json()
    access_token = body.get("access_token")
    if not access_token:
        raise LwaAuthError(f"LWA token response did not include an access_token: {body}")

    return access_token