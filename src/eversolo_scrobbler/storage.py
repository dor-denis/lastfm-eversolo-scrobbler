from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Track


class ScrobbleQueue:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS pending ("
            "id INTEGER PRIMARY KEY, started_at INTEGER NOT NULL, track TEXT NOT NULL, "
            "created_at INTEGER NOT NULL DEFAULT (unixepoch()))"
        )
        self.connection.commit()

    def add(self, track: Track, started_at: int) -> None:
        encoded = json.dumps(
            {
                "artist": track.artist,
                "title": track.title,
                "album": track.album,
                "duration": track.duration,
                "track_number": track.track_number,
                "mbid": track.mbid,
            },
            ensure_ascii=False,
        )
        self.connection.execute(
            "INSERT INTO pending(started_at, track) VALUES (?, ?)", (started_at, encoded)
        )
        self.connection.commit()

    def first(self) -> tuple[int, Track, int] | None:
        row = self.connection.execute(
            "SELECT id, track, started_at FROM pending ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), Track(**json.loads(row[1])), int(row[2])

    def remove(self, item_id: int) -> None:
        self.connection.execute("DELETE FROM pending WHERE id = ?", (item_id,))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
