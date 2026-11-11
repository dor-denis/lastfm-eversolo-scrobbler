# Changelog

## 0.1.2

- Ignore stale track metadata while Eversolo is stopped or paused instead of
  sending it to Last.fm as now playing. Start tracking only when playback begins.
- Exclude paused time when playback resumes and require the playing state before
  queuing a new scrobble. Previously eligible pending scrobbles still retry.

Validation: 27 tests pass. Verified on the Raspberry Pi against Eversolo's live
stopped response with retained track metadata, using a fake Last.fm client.

## 0.1.1

- Fix repeat listens being permanently suppressed after a song's first scrobble.
  Each detected play is queued once; later listens can scrobble again.
  Existing databases remain compatible without resetting their pending queue.
- Recover from Eversolo and Last.fm HTTP timeouts without crashing the daemon.
  Pending scrobbles remain queued for retry after temporary Last.fm failures.

Validation: 21 tests pass, including repeat playback, legacy database history,
pending submissions surviving restarts, and HTTP timeout handling.
