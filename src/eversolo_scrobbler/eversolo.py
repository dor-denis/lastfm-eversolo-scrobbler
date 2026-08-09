from __future__ import annotations

from typing import Any

import aiohttp

from .models import Playback, Track


class EversoloError(Exception):
    pass


class EversoloClient:
    """Read playback state from Eversolo's local, undocumented HTTP API."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        self.url = f"http://{host}:{port}/ZidooMusicControl/v2/getState"
        self.session = session

    async def playback(self) -> Playback:
        try:
            async with self.session.get(self.url) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError) as exc:
            raise EversoloError(str(exc)) from exc
        if not isinstance(payload, dict):
            raise EversoloError("getState returned a non-object response")
        return parse_playback(payload)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _seconds(value: Any, *, allow_zero: bool = False) -> int | None:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    if milliseconds > 0 or (allow_zero and milliseconds == 0):
        return milliseconds // 1000
    return None


def parse_playback(state: dict[str, Any]) -> Playback:
    """Translate internal-player and external-app playback response shapes."""
    raw_state = state.get("state")
    try:
        raw_state = int(raw_state)
    except (TypeError, ValueError):
        raw_state = None
    play_type = state.get("playType")
    external_info = (state.get("everSoloPlayInfo") or {}).get("everSoloPlayAudioInfo") or {}
    if play_type is not None and play_type != 5:
        # Bluetooth, Connect and Android music apps use this live metadata block. The
        # playingMusic block can remain populated with a stale internal-player track.
        # Never fall back to it for an external app, even when that app omits required
        # metadata (Apple Classical currently omits artistName on Eversolo firmware).
        info = external_info
        artist, title, album = info.get("artistName"), info.get("songName"), info.get("albumName")
        mbid = track_number = None
    elif play_type == 5:
        info = state.get("playingMusic") or {}
        artist, title, album = info.get("artist"), info.get("title"), info.get("album")
        mbid = info.get("mbid")
        track_number = info.get("trackNumber")
    else:
        # Some firmware omits playType but still exposes one of the known metadata blocks.
        info = state.get("playingMusic") or {}
        artist, title, album = info.get("artist"), info.get("title"), info.get("album")
        mbid = info.get("mbid")
        track_number = info.get("trackNumber")
    artist, title, album = _clean(artist), _clean(title), _clean(album)
    track = None
    if artist and title:
        try:
            parsed_number = int(track_number) if track_number is not None else None
        except (TypeError, ValueError):
            parsed_number = None
        track = Track(
            artist, title, album, _seconds(state.get("duration")), parsed_number, _clean(mbid)
        )
    position = _seconds(state.get("position"), allow_zero=True)
    external_play_status = (state.get("everSoloPlayInfo") or {}).get("playStatus")
    # Connect playback on tested PLAY firmware reports global state=4 (normally paused)
    # even while its position advances. For playType 6, playStatus=2 is the reliable
    # source-specific playing signal.
    connect_playing = play_type == 6 and external_play_status == 2
    return Playback(
        track=track,
        playing=raw_state == 3 or connect_playing,
        position=position,
        raw_state=raw_state,
    )
