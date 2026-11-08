# Changelog

## 0.1.1

- Fix repeat listens being permanently suppressed after a song's first scrobble.
  Each detected play is queued once; later listens can scrobble again.
  Existing databases remain compatible without resetting their pending queue.
- Recover from Eversolo and Last.fm HTTP timeouts without crashing the daemon.
  Pending scrobbles remain queued for retry after temporary Last.fm failures.

Validation: 21 tests pass, including repeat playback, legacy database history,
pending submissions surviving restarts, and HTTP timeout handling.
