from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from .lastfm import LastfmError
from .models import Playback, Track
from .storage import ScrobbleQueue

LOG = logging.getLogger(__name__)


class Submitter(Protocol):
    async def now_playing(self, track: Track) -> None: ...
    async def scrobble(self, track: Track, started_at: int) -> None: ...


@dataclass(slots=True)
class ActiveTrack:
    track: Track
    started_at: int
    listened: float
    last_tick: float
    last_position: float | None
    queued: bool = False


class ScrobbleEngine:
    """Track actual playing time; pauses and ordinary seeks do not inflate it."""

    def __init__(self, lastfm: Submitter, queue: ScrobbleQueue) -> None:
        self.lastfm, self.queue = lastfm, queue
        self.active: ActiveTrack | None = None

    async def observe(
        self, playback: Playback, *, monotonic: float | None = None, wall_time: float | None = None
    ) -> None:
        now = time.monotonic() if monotonic is None else monotonic
        wall = time.time() if wall_time is None else wall_time
        track = playback.track
        replayed = bool(
            track
            and self.active
            and track.identity == self.active.track.identity
            and playback.playing
            and playback.position is not None
            and self.active.last_position is not None
            and playback.position + 5 < self.active.last_position
        )
        changed = (
            track is None or self.active is None or track.identity != self.active.track.identity
        )
        if track is not None and (changed or replayed):
            self.active = ActiveTrack(
                track, int(wall - (playback.position or 0)), 0.0, now, playback.position
            )
            LOG.info("Now playing: %s — %s", track.artist, track.title)
            try:
                await self.lastfm.now_playing(track)
            except LastfmError as exc:
                # Last.fm explicitly says not to retry failed now-playing notifications.
                LOG.warning("Now-playing update failed: %s", exc)
        elif track is None:
            self.active = None
            return
        elif self.active is not None:
            # Metadata fields sometimes arrive over several polls. Keep the richer latest value.
            self.active.track = track

        active = self.active
        if active is None:
            return
        elapsed = max(0.0, min(now - active.last_tick, 30.0))
        if playback.playing:
            active.listened += elapsed
        active.last_tick = now
        active.last_position = playback.position
        threshold = min((active.track.duration or 0) / 2, 240)
        if (
            active.track.duration
            and active.track.duration > 30
            and active.listened >= threshold
            and not active.queued
        ):
            self.queue.add(active.track, active.started_at)
            active.queued = True
            LOG.info("Queued scrobble: %s — %s", active.track.artist, active.track.title)
        await self.flush_one()

    async def flush_one(self) -> None:
        item = self.queue.first()
        if item is None:
            return
        item_id, track, started_at = item
        try:
            await self.lastfm.scrobble(track, started_at)
        except LastfmError as exc:
            if not exc.retryable:
                LOG.error(
                    "Discarding rejected scrobble %s — %s: %s", track.artist, track.title, exc
                )
                self.queue.remove(item_id)
            else:
                LOG.warning("Scrobble deferred: %s", exc)
        else:
            self.queue.remove(item_id)
            LOG.info("Scrobbled: %s — %s", track.artist, track.title)
