# Eversolo Last.fm scrobbler

A small, headless Python daemon that reads playback metadata directly from an Eversolo streamer on the local network and submits it to Last.fm. Home Assistant is not required.

The Eversolo interface used here is the same local HTTP interface used by the community [Eversolo Home Assistant integration](https://github.com/hchris1/Eversolo). It is not a published vendor SDK, so firmware changes may require parser updates. The current parser handles the internal player, Bluetooth, and Spotify Connect response shapes known to that integration.

Apple Music is supported when Eversolo supplies artist and title metadata. Apple Classical currently leaves `artistName` empty on tested PLAY firmware, so those items are deliberately skipped rather than incorrectly scrobbling stale metadata from a previous playback source.

## Scrobbling behaviour

- Sends `track.updateNowPlaying` when a new play is detected, followed by one confirmation refresh after 15 seconds to handle an occasionally accepted-but-not-visible Last.fm update.
- Scrobbles only tracks longer than 30 seconds, after listening to half the track or four minutes, whichever comes first.
- Counts elapsed playing time rather than trusting the seek position, so pauses and forward seeks do not create false scrobbles.
- Detects replay of the same track when its position moves backwards.
- Stores eligible submissions in SQLite before sending. Pending submissions survive restarts and temporary Last.fm/network failures.
- Does not retry failed now-playing updates, and only retries Last.fm error codes documented as temporary.

These rules follow Last.fm's [Scrobbling 2.0 guidance](https://www.last.fm/api/scrobbling).

## Quick installation

On Raspberry Pi OS Bookworm or newer, clone the project and run the interactive installer:

```sh
git clone https://github.com/dor-denis/lastfm-eversolo-scrobbler.git
cd lastfm-eversolo-scrobbler
sudo ./install.sh
```

The installer asks for the Eversolo IP address, Last.fm API key, and shared secret (twice to catch hidden-input typos). It prints a Last.fm approval link; open it, approve access, then press Enter. Everything else—the service user, Python environment, protected configuration, and automatic startup—is handled for you.

The generated configuration is owned by `root:eversolo-scrobbler` with mode `0640`: root may edit it, the daemon may read it, and other users have no access.

Create an API key first at [last.fm/api/account/create](https://www.last.fm/api/account/create). After installation, use these two commands when needed:

```sh
sudo systemctl status eversolo-scrobbler
sudo journalctl -u eversolo-scrobbler -f
```

After `git pull`, re-running `sudo ./install.sh` updates the application while preserving the existing configuration.

## Manual/development configuration

`config.example.toml` contains placeholders and is intentionally tracked. Local runtime files named `config.toml` or `eversolo-scrobbler.toml`, `.env` files, and SQLite sidecar files are ignored by Git. Never put real Last.fm credentials into `config.example.toml` or another tracked file.

For a local development configuration, copy the example to the ignored filename:

```sh
cp config.example.toml config.toml
chmod 600 config.toml
$EDITOR config.toml
eversolo-scrobbler --config ./config.toml inspect
```

To inspect the raw player metadata on an installed system:

```sh
/opt/eversolo-scrobbler/venv/bin/eversolo-scrobbler \
  --config /etc/eversolo-scrobbler.toml inspect
```

While a track is playing, the output should contain `state: 3`, a duration in milliseconds, and either `playingMusic` or `everSoloPlayInfo` metadata.

For a foreground test, run `eversolo-scrobbler --config ./config.toml --verbose`. Stop with Ctrl-C. Do not place credentials directly on a command line, because command arguments may be visible to other local users.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

The daemon deliberately has one runtime dependency (`aiohttp`) and uses SQLite from the standard library, which keeps it suitable for a Raspberry Pi Zero 2 W.
