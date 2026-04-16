"""Binance signing helpers."""

import hashlib
import hmac


def sign_query(query_string: str, secret: str) -> str:
    """Return HMAC SHA256 signature for Binance signed endpoints."""

    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()
