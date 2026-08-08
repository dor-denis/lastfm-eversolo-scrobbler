# Eversolo Last.fm scrobbler

A small, headless Python daemon that reads playback metadata directly from an Eversolo streamer on the local network and submits it to Last.fm. Home Assistant is not required.

The Eversolo interface used here is the same local HTTP interface used by the community [Eversolo Home Assistant integration](https://github.com/hchris1/Eversolo). It is not a published vendor SDK, so firmware changes may require parser updates. The current parser handles the internal player, Bluetooth, and Spotify Connect response shapes known to that integration.

## Scrobbling behaviour

- Sends `track.updateNowPlaying` once when a new play is detected.
- Scrobbles only tracks longer than 30 seconds, after listening to half the track or four minutes, whichever comes first.
- Counts elapsed playing time rather than trusting the seek position, so pauses and forward seeks do not create false scrobbles.
- Detects replay of the same track when its position moves backwards.
- Stores eligible submissions in SQLite before sending. Pending submissions survive restarts and temporary Last.fm/network failures.
- Does not retry failed now-playing updates, and only retries Last.fm error codes documented as temporary.

These rules follow Last.fm's [Scrobbling 2.0 guidance](https://www.last.fm/api/scrobbling).

## Install and configure

Raspberry Pi OS Bookworm or newer (Python 3.11+) is recommended. On the Pi:

```sh
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin eversolo-scrobbler
sudo mkdir -p /opt/eversolo-scrobbler
sudo chown "$USER" /opt/eversolo-scrobbler
python3 -m venv /opt/eversolo-scrobbler/venv
/opt/eversolo-scrobbler/venv/bin/pip install /path/to/this/repository
sudo cp config.example.toml /etc/eversolo-scrobbler.toml
sudo chmod 600 /etc/eversolo-scrobbler.toml
```

`config.example.toml` contains placeholders and is intentionally tracked. Local runtime files named `config.toml` or `eversolo-scrobbler.toml`, `.env` files, and SQLite sidecar files are ignored by Git. Never put real Last.fm credentials into `config.example.toml` or another tracked file. Before committing, verify with `git status` that no credential-bearing file is staged.

Create a Last.fm API account at [last.fm/api/account/create](https://www.last.fm/api/account/create). Put its API key and shared secret in the config temporarily, then authorize the application from an interactive shell:

```sh
/opt/eversolo-scrobbler/venv/bin/eversolo-scrobbler auth \
  --api-key YOUR_KEY --api-secret YOUR_SECRET
```

Open the printed URL, approve it, press Enter, then copy the resulting session key into `/etc/eversolo-scrobbler.toml`. Edit `eversolo.host` to the PLAY's static/DHCP-reserved IP. Secrets can instead be supplied through `LASTFM_API_KEY`, `LASTFM_API_SECRET`, and `LASTFM_SESSION_KEY` environment variables.

For a local development configuration, copy the example to the ignored filename:

```sh
cp config.example.toml config.toml
chmod 600 config.toml
$EDITOR config.toml
eversolo-scrobbler --config ./config.toml inspect
```

Before enabling the daemon, verify that this PLAY firmware exposes usable metadata:

```sh
/opt/eversolo-scrobbler/venv/bin/eversolo-scrobbler \
  --config /etc/eversolo-scrobbler.toml inspect
```

While a track is playing, the output should contain `state: 3`, a duration in milliseconds, and either `playingMusic` or `everSoloPlayInfo` metadata. Then install the service:

```sh
sudo cp deploy/eversolo-scrobbler.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eversolo-scrobbler
sudo journalctl -u eversolo-scrobbler -f
```

For a foreground test, run `eversolo-scrobbler --config ./config.toml --verbose`. Stop with Ctrl-C. Do not place credentials directly on a command line, because command arguments may be visible to other local users.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

The daemon deliberately has one runtime dependency (`aiohttp`) and uses SQLite from the standard library, which keeps it suitable for a Raspberry Pi Zero 2 W.
