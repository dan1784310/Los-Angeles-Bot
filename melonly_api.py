"""
Melonly API integration.

This module provides authenticated access to the Melonly API using
MELONLY_API_TOKEN. Docs: https://apidocs.melonly.xyz/
"""

import os
from typing import Any, Dict, Optional
import requests

# Production base URL, confirmed from https://apidocs.melonly.xyz/quickstart
MELONLY_API_BASE_URL = "https://api.melonly.xyz/api/v1"


class MelonlyAPIError(RuntimeError):
    """Raised when a Melonly API request fails."""


class MelonlyClient:
    """Client for the Melonly API."""

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = (api_token or os.getenv("MELONLY_API_TOKEN", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    def _headers(self) -> Dict[str, str]:
        if not self.api_token:
            raise MelonlyAPIError(
                "MELONLY_API_TOKEN environment variable is not configured."
            )
        return {"Authorization": f"Bearer {self.api_token}"}

    def get_server_info(self) -> Dict[str, Any]:
        """
        Fetch basic server info: id, name, discordGuildId, ownerId,
        createdAt, joinCode. This is also the standard way to verify a
        token/connection is working, per Melonly's own quickstart guide.
        """
        try:
            response = requests.get(
                f"{MELONLY_API_BASE_URL}/server/info",
                headers=self._headers(),
                timeout=15,
            )

            try:
                data = response.json()
            except ValueError:
                data = {"message": response.text}

            if not response.ok:
                raise MelonlyAPIError(
                    f"Melonly API returned HTTP {response.status_code}: {data}"
                )

            return data
        except requests.RequestException as e:
            raise MelonlyAPIError(f"Network error contacting Melonly: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the Melonly API connection by fetching server info.
        Returns the server info dict on success; raises MelonlyAPIError
        (with the real reason) if the token or connection is invalid.
        """
        return self.get_server_info()
