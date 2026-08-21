"""
ER:LC API integration.

This module provides:
- Authenticated access to the ER:LC v2 server endpoint using ERLC_SERVER_KEY.
- A signed Event Webhook receiver for supported ER:LC events.

The webhook receiver verifies the Ed25519 signature exactly as required by
the official ER:LC documentation before accepting an event.
"""

import base64
import binascii
import os
from typing import Any, Dict, Optional

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from flask import Request, jsonify

ERLC_API_BASE_URL = "https://api.erlc.gg"
ERLC_SERVER_URL = f"{ERLC_API_BASE_URL}/v2/server"

# Official ER:LC Event Webhook public key (SPKI, base64).
ERLC_WEBHOOK_PUBLIC_KEY_B64 = (
    "MCowBQYDK2VwAyEAjSICb9pp0kHizGQtdG8ySWsDChfGqi+gyFCttigBNOA="
)


class ERLCAPIError(RuntimeError):
    """Raised when an ER:LC API request fails."""


class ERLCClient:
    """Small synchronous client for the ER:LC Private Server API."""

    def __init__(self, server_key: Optional[str] = None):
        self.server_key = (server_key or os.getenv("ERLC_SERVER_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.server_key)

    def _headers(self) -> Dict[str, str]:
        if not self.server_key:
            raise ERLCAPIError(
                "ERLC_SERVER_KEY environment variable is not configured."
            )
        return {"server-key": self.server_key}

    def get_server(self, **query: bool) -> Dict[str, Any]:
        """
        Fetch server information.

        Optional query arguments can be things such as:
        Players=True, Staff=True, CommandLogs=True, etc.
        """
        params = {key: str(value).lower() for key, value in query.items() if value}
        response = requests.get(
            ERLC_SERVER_URL,
            headers=self._headers(),
            params=params,
            timeout=15,
        )

        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}

        if not response.ok:
            raise ERLCAPIError(
                f"ER:LC API returned HTTP {response.status_code}: {data}"
            )

        return data


def _webhook_public_key() -> Ed25519PublicKey:
    raw = base64.b64decode(ERLC_WEBHOOK_PUBLIC_KEY_B64)
    # The ER:LC key is an SPKI/DER public key. The last 32 bytes are the
    # Ed25519 raw public key bytes.
    return Ed25519PublicKey.from_public_bytes(raw[-32:])


def verify_erlc_webhook(request: Request) -> bool:
    """
    Verify an ER:LC Event Webhook request.

    ER:LC signs: UTF-8(timestamp) + raw request body.
    The signature is supplied as hex in X-Signature-Ed25519.
    """
    timestamp = request.headers.get("X-Signature-Timestamp")
    signature_hex = request.headers.get("X-Signature-Ed25519")

    if not timestamp or not signature_hex:
        return False

    try:
        signature = binascii.unhexlify(signature_hex)
    except (binascii.Error, ValueError):
        return False

    raw_body = request.get_data(cache=True, as_text=False)
    message = timestamp.encode("utf-8") + raw_body

    try:
        _webhook_public_key().verify(signature, message)
        return True
    except Exception:
        return False


def handle_erlc_webhook(request: Request):
    """Return a Flask response for an ER:LC Event Webhook request."""
    if not verify_erlc_webhook(request):
        return jsonify({"error": "Invalid ER:LC webhook signature"}), 401

    try:
        payload = request.get_json(silent=False)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "Webhook JSON must be an object"}), 400

    # No Discord commands or automation are performed here yet.
    # The event is only accepted and logged so the integration is ready
    # for future features.
    print(f"[ERLC WEBHOOK] Received event: {payload}")

    return jsonify({"received": True}), 200
