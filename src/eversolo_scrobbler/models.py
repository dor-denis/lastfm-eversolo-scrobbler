from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    artist: str
    title: str
    album: str | None = None
    duration: int | None = None
    track_number: int | None = None
    mbid: str | None = None

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.artist.casefold(), self.title.casefold(), (self.album or "").casefold())


@dataclass(frozen=True, slots=True)
class Playback:
    track: Track | None
    playing: bool
    position: float | None = None
    raw_state: int | None = None
