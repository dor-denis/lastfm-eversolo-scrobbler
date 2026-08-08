from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import aiohttp

from .models import Track

API_URL = "https://ws.audioscrobbler.com/2.0/"


@dataclass(slots=True)
class LastfmError(Exception):
    message: str
    code: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class LastfmClient:
    def __init__(
        self, api_key: str, api_secret: str, session_key: str, session: aiohttp.ClientSession
    ) -> None:
        self.api_key, self.api_secret, self.session_key = api_key, api_secret, session_key
        self.session = session

    def _signed(self, params: dict[str, Any]) -> dict[str, str]:
        result = {key: str(value) for key, value in params.items() if value is not None}
        result.update(api_key=self.api_key, sk=self.session_key)
        signature = "".join(key + result[key] for key in sorted(result)) + self.api_secret
        # Last.fm's protocol mandates MD5 for request signing; this is not password hashing.
        result["api_sig"] = hashlib.md5(signature.encode("utf-8")).hexdigest()
        result["format"] = "json"
        return result

    async def _post(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self.session.post(API_URL, data=self._signed(params)) as response:
                payload = await response.json(content_type=None)
                if response.status >= 500:
                    raise LastfmError(f"Last.fm HTTP {response.status}", retryable=True)
        except (aiohttp.ClientError, ValueError) as exc:
            raise LastfmError(f"Last.fm request failed: {exc}", retryable=True) from exc
        if "error" in payload:
            code = int(payload.get("error", 0))
            # Code 9 must remain queued until the operator replaces the expired session key.
            raise LastfmError(
                str(payload.get("message", "Last.fm API error")), code, code in (9, 11, 16)
            )
        return payload

    @staticmethod
    def _metadata(track: Track) -> dict[str, Any]:
        return {
            "artist": track.artist,
            "track": track.title,
            "album": track.album,
            "duration": track.duration,
            "trackNumber": track.track_number,
            "mbid": track.mbid,
        }

    async def now_playing(self, track: Track) -> None:
        await self._post({"method": "track.updateNowPlaying", **self._metadata(track)})

    async def scrobble(self, track: Track, started_at: int) -> None:
        await self._post(
            {"method": "track.scrobble", "timestamp": started_at, **self._metadata(track)}
        )
