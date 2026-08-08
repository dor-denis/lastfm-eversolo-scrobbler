from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Config:
    eversolo_host: str
    eversolo_port: int
    poll_interval: float
    request_timeout: float
    api_key: str
    api_secret: str
    session_key: str
    database: Path


def load_config(path: Path) -> Config:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"configuration file not found: {path}") from exc
    device = data.get("eversolo", {})
    lastfm = data.get("lastfm", {})
    daemon = data.get("daemon", {})

    def secret(name: str, env: str) -> str:
        return os.environ.get(env, str(lastfm.get(name, ""))).strip()

    host = str(device.get("host", "")).strip()
    api_key = secret("api_key", "LASTFM_API_KEY")
    api_secret = secret("api_secret", "LASTFM_API_SECRET")
    session_key = secret("session_key", "LASTFM_SESSION_KEY")
    missing = [
        name
        for name, value in (
            ("eversolo.host", host),
            ("lastfm.api_key", api_key),
            ("lastfm.api_secret", api_secret),
            ("lastfm.session_key", session_key),
        )
        if not value
    ]
    if missing:
        raise ValueError("missing configuration: " + ", ".join(missing))
    return Config(
        eversolo_host=host,
        eversolo_port=int(device.get("port", 9529)),
        poll_interval=float(daemon.get("poll_interval", 2.0)),
        request_timeout=float(daemon.get("request_timeout", 5.0)),
        api_key=api_key,
        api_secret=api_secret,
        session_key=session_key,
        database=Path(str(daemon.get("database", "/var/lib/eversolo-scrobbler/state.db"))),
    )
