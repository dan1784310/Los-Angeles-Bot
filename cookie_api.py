"""
Cookie API integration for hosted Discord transcripts and Roblox group
management.

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
    """Raised when a Cookie API request fails."""


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


COOKIE_GROUP_REQUESTS_PATH = "/api/roblox/group/join-requests"


def _get_workspace_id(workspace_id: Optional[int] = None) -> str:
    value = workspace_id or os.getenv("COOKIE_WORKSPACE_ID")
    value = str(value or "").strip()
    if not value:
        raise CookieAPIError(
            "COOKIE_WORKSPACE_ID is not configured. Add the Cookie API "
            "Group Manager workspace ID to the bot environment."
        )
    return value


async def _group_request(
    method: str,
    workspace_id: Optional[int],
    json_payload: Optional[dict] = None,
) -> Any:
    api_key = _get_api_key()
    workspace = _get_workspace_id(workspace_id)
    url = f"{COOKIE_API_BASE_URL}{COOKIE_GROUP_REQUESTS_PATH}"
    headers = {
        "Authorization": api_key,
        "Accept": "application/json",
    }
    request_kwargs = {
        "params": {"workspace_id": workspace},
        "headers": headers,
    }
    if json_payload is not None:
        request_kwargs["json"] = json_payload

    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, **request_kwargs) as response:
                response_text = await response.text()
                try:
                    payload = json.loads(response_text)
                except (TypeError, ValueError):
                    payload = None

                if response.status >= 400:
                    detail = _response_message(
                        payload,
                        f"HTTP {response.status} from Cookie API.",
                    )
                    raise CookieAPIError(
                        f"Cookie API group request failed: {detail}"
                    )

                if isinstance(payload, dict) and payload.get("success") is False:
                    detail = _response_message(
                        payload,
                        "Cookie API rejected the group request.",
                    )
                    raise CookieAPIError(
                        f"Cookie API group request failed: {detail}"
                    )

                return payload
    except CookieAPIError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CookieAPIError(
            f"Could not reach Cookie API: {type(e).__name__}."
        ) from e


def _normalize_join_request(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    requester = item.get("requester")
    if not isinstance(requester, dict):
        requester = item.get("user") if isinstance(item.get("user"), dict) else {}

    raw_user_id = (
        requester.get("userId")
        or requester.get("user_id")
        or item.get("userId")
        or item.get("user_id")
        or item.get("id")
    )
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    username = (
        requester.get("username")
        or item.get("username")
        or f"User-{user_id}"
    )
    display_name = (
        requester.get("displayName")
        or requester.get("display_name")
        or username
    )
    created = (
        item.get("created")
        or item.get("created_at")
        or item.get("requested_at")
    )
    return {
        "user_id": user_id,
        "username": str(username)[:80],
        "display_name": str(display_name)[:80],
        "created_at": str(created) if created else None,
        "has_verified_badge": bool(
            requester.get("hasVerifiedBadge")
            or requester.get("has_verified_badge")
        ),
    }


async def list_group_join_requests(
    workspace_id: Optional[int] = None,
) -> list[dict]:
    payload = await _group_request(
        "GET",
        workspace_id,
    )
    if isinstance(payload, dict):
        raw_requests = payload.get("requests", [])
    elif isinstance(payload, list):
        raw_requests = payload
    else:
        raw_requests = []

    if not isinstance(raw_requests, list):
        raise CookieAPIError("Cookie API returned an invalid request list.")

    normalized = []
    for item in raw_requests:
        request = _normalize_join_request(item)
        if request is not None:
            normalized.append(request)
    return normalized


async def accept_group_join_request(
    user_id: int,
    workspace_id: Optional[int] = None,
    rank_position: Optional[int] = None,
) -> Any:
    payload = {"user_id": int(user_id)}
    if rank_position is not None:
        payload["rank_position"] = int(rank_position)
    return await _group_request(
        "POST",
        workspace_id,
        json_payload=payload,
    )


async def deny_group_join_request(
    user_id: int,
    workspace_id: Optional[int] = None,
) -> Any:
    return await _group_request(
        "DELETE",
        workspace_id,
        json_payload={"user_id": int(user_id)},
    )
