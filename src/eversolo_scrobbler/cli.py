from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import signal
from pathlib import Path

import aiohttp

from .auth import authenticate
from .config import load_config
from .engine import ScrobbleEngine
from .eversolo import EversoloClient, EversoloError
from .lastfm import LastfmClient
from .storage import ScrobbleQueue

LOG = logging.getLogger(__name__)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="eversolo-scrobbler")
    result.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("EVERSOLO_SCROBBLER_CONFIG", "/etc/eversolo-scrobbler.toml")),
    )
    result.add_argument("--verbose", action="store_true")
    commands = result.add_subparsers(dest="command")
    auth = commands.add_parser("auth", help="create a Last.fm session key")
    auth.add_argument("--api-key", default=os.environ.get("LASTFM_API_KEY"))
    auth.add_argument("--api-secret", default=os.environ.get("LASTFM_API_SECRET"))
    commands.add_parser("configure", help="interactively create a protected configuration file")
    commands.add_parser("inspect", help="print one raw Eversolo state response")
    return result


def _toml_string(value: str) -> str:
    """JSON strings are valid TOML basic strings and provide correct escaping."""
    return json.dumps(value, ensure_ascii=False)


async def configure(path: Path, timeout: aiohttp.ClientTimeout) -> None:
    print("Eversolo Scrobbler setup\n")
    host = input("Eversolo IP address: ").strip()
    api_key = input("Last.fm API key: ").strip()
    api_secret = getpass.getpass("Last.fm shared secret: ").strip()
    if not host or not api_key or not api_secret:
        raise ValueError("IP address, API key, and shared secret are required")
    async with aiohttp.ClientSession(timeout=timeout) as session:
        session_key = await authenticate(api_key, api_secret, session)
    contents = f"""[eversolo]
host = {_toml_string(host)}
port = 9529

[lastfm]
api_key = {_toml_string(api_key)}
api_secret = {_toml_string(api_secret)}
session_key = {_toml_string(session_key)}

[daemon]
poll_interval = 2.0
request_timeout = 5.0
database = "/var/lib/eversolo-scrobbler/state.db"
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(contents, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    print(f"\nConfiguration written to {path}")


async def run(args: argparse.Namespace) -> int:
    timeout = aiohttp.ClientTimeout(total=10)
    if args.command == "auth":
        if not args.api_key or not args.api_secret:
            raise ValueError(
                "auth requires --api-key and --api-secret (or matching environment variables)"
            )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            key = await authenticate(args.api_key, args.api_secret, session)
        print(f"Session key (store this securely):\n{key}")
        return 0
    if args.command == "configure":
        await configure(args.config, timeout)
        return 0

    config = load_config(args.config)
    timeout = aiohttp.ClientTimeout(total=config.request_timeout)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        device = EversoloClient(config.eversolo_host, config.eversolo_port, session)
        if args.command == "inspect":
            async with session.get(device.url) as response:
                response.raise_for_status()
                print(
                    json.dumps(await response.json(content_type=None), indent=2, ensure_ascii=False)
                )
            return 0
        queue = ScrobbleQueue(config.database)
        lastfm = LastfmClient(config.api_key, config.api_secret, config.session_key, session)
        engine = ScrobbleEngine(lastfm, queue)
        stopping = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopping.set)
        try:
            while not stopping.is_set():
                try:
                    await engine.observe(await device.playback())
                except EversoloError as exc:
                    LOG.warning("Eversolo unavailable: %s", exc)
                    await engine.flush_one()
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=config.poll_interval)
                except TimeoutError:
                    pass
        finally:
            queue.close()
    return 0


def main() -> None:
    args = parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (ValueError, OSError) as exc:
        parser().error(str(exc))
