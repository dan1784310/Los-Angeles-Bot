"""
Cookie API integration for hosted Discord transcripts.

The API key is read from the COOKIE_API_KEY environment variable. The bot
token is read from the normal TOKEN config, or COOKIE_BOT_TOKEN when provided.
Secrets are never logged.
"""

import asyncio
import json
import os
from typing import Any, Optional

import aiohttp

from config import TOKEN


COOKIE_API_BASE_URL = "https://api.cookie-api.com"
COOKIE_TRANSCRIPT_PATH = "/api/transcript"


class CookieAPIError(RuntimeError):
    """Raised when Cookie API cannot create a hosted transcript."""


def _get_api_key() -> str:
    api_key = (os.getenv("COOKIE_API_KEY") or "").strip()
    if not api_key:
        raise CookieAPIError("COOKIE_API_KEY is not configured.")
    return api_key


def _get_bot_token(explicit_token: Optional[str] = None) -> str:
    token = (
        explicit_token
        or os.getenv("COOKIE_BOT_TOKEN")
        or TOKEN
        or ""
    ).strip()
    if not token:
        raise CookieAPIError(
            "No bot token is configured for Cookie API transcripts."
        )
    return token


def _response_message(payload: Any, fallback: str) -> str:
    if not isinstance(payload, dict):
        return fallback

    message = payload.get("message")
    if isinstance(message, str) and message:
        return message[:240]

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        first_error = errors[0]
        if isinstance(first_error, dict):
            error_message = first_error.get("message")
            if isinstance(error_message, str) and error_message:
                return error_message[:240]

    return fallback


async def create_transcript_url(
    channel_id: int,
    name: str,
    bot_token: Optional[str] = None,
) -> str:
    """Create a hosted Cookie API transcript and return its public URL."""
    api_key = _get_api_key()
    token = _get_bot_token(bot_token)
    transcript_name = " ".join(str(name).split())[:100]
    if not transcript_name:
        raise CookieAPIError("The transcript name cannot be empty.")

    url = f"{COOKIE_API_BASE_URL}{COOKIE_TRANSCRIPT_PATH}"
    params = {
        "channel_id": str(channel_id),
        "name": transcript_name,
    }
    payload = {
        "bot_token": token,
        "name": transcript_name,
    }
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                params=params,
                json=payload,
                headers=headers,
            ) as response:
                response_text = await response.text()
                try:
                    response_data = json.loads(response_text)
                except (TypeError, ValueError):
                    response_data = None

                if response.status >= 400:
                    detail = _response_message(
                        response_data,
                        f"HTTP {response.status} from Cookie API.",
                    )
                    raise CookieAPIError(
                        f"Cookie API transcript creation failed: {detail}"
                    )

                if not isinstance(response_data, dict):
                    raise CookieAPIError(
                        "Cookie API returned an invalid transcript response."
                    )

                if response_data.get("success") is False:
                    detail = _response_message(
                        response_data,
                        "Cookie API rejected the transcript request.",
                    )
                    raise CookieAPIError(
                        f"Cookie API transcript creation failed: {detail}"
                    )

                transcript_url = response_data.get("url")
                if not isinstance(transcript_url, str) or not transcript_url:
                    data = response_data.get("data")
                    if isinstance(data, dict):
                        transcript_url = data.get("url")

                if not isinstance(transcript_url, str) or not transcript_url.startswith(
                    ("http://", "https://")
                ):
                    raise CookieAPIError(
                        "Cookie API did not return a valid transcript URL."
                    )

                return transcript_url
    except CookieAPIError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CookieAPIError(
            f"Could not reach Cookie API: {type(e).__name__}."
        ) from e
