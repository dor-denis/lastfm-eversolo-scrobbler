from __future__ import annotations

import hashlib
from typing import Any

import aiohttp

from .lastfm import API_URL, LastfmError


def _signed(params: dict[str, Any], api_key: str, secret: str) -> dict[str, str]:
    values = {key: str(value) for key, value in params.items()}
    values["api_key"] = api_key
    source = "".join(key + values[key] for key in sorted(values)) + secret
    # Last.fm's protocol mandates MD5 for request signing; this is not password hashing.
    values["api_sig"] = hashlib.md5(source.encode()).hexdigest()
    values["format"] = "json"
    return values


async def authenticate(api_key: str, api_secret: str, session: aiohttp.ClientSession) -> str:
    async with session.get(
        API_URL, params=_signed({"method": "auth.getToken"}, api_key, api_secret)
    ) as response:
        payload = await response.json(content_type=None)
    if "token" not in payload:
        raise LastfmError(str(payload.get("message", "could not obtain authentication token")))
    token = str(payload["token"])
    print(
        f"Open this URL and approve access:\nhttps://www.last.fm/api/auth/?api_key={api_key}&token={token}"
    )
    input("Press Enter after approving access... ")
    async with session.get(
        API_URL, params=_signed({"method": "auth.getSession", "token": token}, api_key, api_secret)
    ) as response:
        payload = await response.json(content_type=None)
    try:
        return str(payload["session"]["key"])
    except (KeyError, TypeError) as exc:
        code = payload.get("error")
        message = str(payload.get("message", "could not create session"))
        if code is not None:
            message = f"Last.fm authentication failed (error {code}): {message}"
        raise LastfmError(message, int(code) if code is not None else None) from exc
