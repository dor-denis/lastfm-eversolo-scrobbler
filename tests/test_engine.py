from pathlib import Path

import pytest

from eversolo_scrobbler.engine import ScrobbleEngine
from eversolo_scrobbler.eversolo import parse_playback
from eversolo_scrobbler.lastfm import LastfmError
from eversolo_scrobbler.models import Playback, Track
from eversolo_scrobbler.storage import ScrobbleQueue


class FakeLastfm:
    def __init__(self) -> None:
        self.now = []
        self.scrobbles = []

    async def now_playing(self, track: Track) -> None:
        self.now.append(track)

    async def scrobble(self, track: Track, started_at: int) -> None:
        self.scrobbles.append((track, started_at))


async def test_scrobbles_after_half_the_track(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    track = Track("Artist", "Title", duration=100)
    await engine.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 25), monotonic=25, wall_time=1_025)
    await engine.observe(Playback(track, False, 25), monotonic=35, wall_time=1_035)
    await engine.observe(Playback(track, True, 25), monotonic=40, wall_time=1_040)
    assert not lastfm.scrobbles
    await engine.observe(Playback(track, True, 50), monotonic=65, wall_time=1_065)
    assert len(lastfm.now) == 2
    assert [(item[0].title, item[1]) for item in lastfm.scrobbles] == [("Title", 1_000)]


@pytest.mark.parametrize("state", [0, 4])
async def test_inactive_metadata_never_starts_a_play(tmp_path: Path, state: int) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    # Stopped PLAY firmware retains the last internal player's metadata.
    playback = parse_playback(
        {
            "state": state,
            "playType": 5,
            "position": 0,
            "duration": 517191,
            "playingMusic": {
                "artist": "Wolves In The Throne Room",
                "title": "Knights of Tiamat",
                "album": "Estuary",
            },
            "everSoloPlayInfo": {"playStatus": 0},
        }
    )
    for tick in range(0, 601, 10):
        await engine.observe(playback, monotonic=tick, wall_time=1_000 + tick)
    assert lastfm.now == []
    assert lastfm.scrobbles == []
    assert engine.active is None
    assert queue.first() is None
    queue.close()


async def test_stopped_metadata_change_waits_for_playback(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    current = Track("The Strokes", "Ode To The Mets", duration=100)
    stale = Track("Wolves In The Throne Room", "Knights of Tiamat", duration=100)
    await engine.observe(Playback(current, True, 0), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(stale, False, 0), monotonic=10, wall_time=1_010)
    await engine.observe(Playback(stale, False, 0), monotonic=300, wall_time=1_300)
    assert lastfm.now == [current]
    assert lastfm.scrobbles == []
    assert engine.active is None

    await engine.observe(Playback(stale, True, 0), monotonic=310, wall_time=1_310)
    await engine.observe(Playback(stale, True, 25), monotonic=335, wall_time=1_335)
    assert lastfm.scrobbles == []
    await engine.observe(Playback(stale, True, 50), monotonic=360, wall_time=1_360)
    assert lastfm.now == [current, stale, stale]
    assert lastfm.scrobbles == [(stale, 1_310)]
    queue.close()


async def test_pause_does_not_count_as_listening_or_send_confirmation(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    track = Track("Artist", "Title", duration=100)
    for tick, playing, position in [
        (0, True, 0), (10, True, 10), (12, False, 10),
        (300, False, 10), (330, True, 10), (350, True, 30),
    ]:
        await engine.observe(
            Playback(track, playing, position), monotonic=tick, wall_time=1_000 + tick
        )
        if not playing:
            assert lastfm.now == [track]
        assert lastfm.scrobbles == []
    await engine.observe(Playback(track, True, 50), monotonic=370, wall_time=1_370)
    assert lastfm.now == [track, track]
    assert lastfm.scrobbles == [(track, 1_000)]
    queue.close()


async def test_inactive_metadata_does_not_block_pending_scrobbles(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    track = Track("Artist", "Previously listened", duration=100)
    queue.add(track, 900)
    engine = ScrobbleEngine(lastfm, queue)
    await engine.observe(Playback(track, False, 0), monotonic=0, wall_time=1_000)
    assert lastfm.now == []
    assert lastfm.scrobbles == [(track, 900)]
    assert queue.first() is None
    queue.close()


async def test_duration_arriving_while_paused_does_not_queue_a_scrobble(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    track = Track("Artist", "Title")
    await engine.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 20), monotonic=20, wall_time=1_020)
    enriched = Track("Artist", "Title", duration=40)
    await engine.observe(Playback(enriched, False, 20), monotonic=30, wall_time=1_030)
    assert lastfm.scrobbles == []
    assert queue.first() is None
    await engine.observe(Playback(enriched, True, 20), monotonic=100, wall_time=1_100)
    assert lastfm.scrobbles == [(enriched, 1_000)]
    queue.close()


async def test_short_track_is_never_scrobbled(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    engine = ScrobbleEngine(lastfm, ScrobbleQueue(tmp_path / "state.db"))
    track = Track("Artist", "Jingle", duration=30)
    await engine.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 30), monotonic=30, wall_time=1_030)
    assert not lastfm.scrobbles


async def test_position_rollback_starts_a_new_play(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    engine = ScrobbleEngine(lastfm, ScrobbleQueue(tmp_path / "state.db"))
    track = Track("Artist", "Repeat", duration=200)
    await engine.observe(Playback(track, True, 180), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 190), monotonic=12, wall_time=1_012)
    await engine.observe(Playback(track, True, 2), monotonic=14, wall_time=1_014)
    assert len(lastfm.now) == 2
    assert engine.active is not None and engine.active.started_at == 1_012


async def test_position_reset_just_after_track_change_is_not_a_replay(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    engine = ScrobbleEngine(lastfm, ScrobbleQueue(tmp_path / "state.db"))
    track = Track("Fontaines D.C.", "Starburster", duration=221)
    await engine.observe(Playback(track, True, 180), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 2), monotonic=3, wall_time=1_003)
    assert lastfm.now == [track]
    assert engine.active is not None and engine.active.started_at == 1_001


async def test_now_playing_gets_one_confirmation_refresh(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    engine = ScrobbleEngine(lastfm, ScrobbleQueue(tmp_path / "state.db"))
    track = Track("Chelsea Wolfe", "Salt", duration=263)
    await engine.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await engine.observe(Playback(track, True, 14), monotonic=14, wall_time=1_014)
    await engine.observe(Playback(track, True, 16), monotonic=16, wall_time=1_016)
    await engine.observe(Playback(track, True, 30), monotonic=30, wall_time=1_030)
    assert lastfm.now == [track, track]


async def test_repeat_listen_is_scrobbled_after_restart_with_legacy_history(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    lastfm = FakeLastfm()
    first_queue = ScrobbleQueue(database)
    first = ScrobbleEngine(lastfm, first_queue)
    track = Track("King Gizzard & The Lizard Wizard", "Uqt", "Album One", duration=100)
    await first.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await first.observe(Playback(track, True, 25), monotonic=25, wall_time=1_025)
    await first.observe(Playback(track, True, 50), monotonic=50, wall_time=1_050)
    # Reproduce the permanent suppression history left by older installations.
    first_queue.connection.execute(
        "CREATE TABLE submitted (artist_key TEXT, title_key TEXT, submitted_at INTEGER)"
    )
    first_queue.connection.execute(
        "INSERT INTO submitted VALUES (?, ?, ?)",
        (track.artist.casefold(), track.title.casefold(), 1_050),
    )
    first_queue.connection.commit()
    first_queue.close()

    second_queue = ScrobbleQueue(database)
    second = ScrobbleEngine(lastfm, second_queue)
    same_song_different_case_and_album = Track(
        " king gizzard & the lizard wizard ", "UQT", "Album Two", duration=100
    )
    await second.observe(
        Playback(same_song_different_case_and_album, True, 0),
        monotonic=100,
        wall_time=2_000,
    )
    await second.observe(
        Playback(same_song_different_case_and_album, True, 25),
        monotonic=125,
        wall_time=2_025,
    )
    await second.observe(
        Playback(same_song_different_case_and_album, True, 50),
        monotonic=150,
        wall_time=2_050,
    )

    assert [(track.artist, track.title) for track, _ in lastfm.scrobbles] == [
        ("King Gizzard & The Lizard Wizard", "Uqt"),
        (same_song_different_case_and_album.artist, same_song_different_case_and_album.title),
    ]
    assert second_queue.first() is None
    second_queue.close()


async def test_repeat_same_track_scrobbles_once_per_play(tmp_path: Path) -> None:
    lastfm = FakeLastfm()
    queue = ScrobbleQueue(tmp_path / "state.db")
    engine = ScrobbleEngine(lastfm, queue)
    track = Track("Chelsea Wolfe", "Spun", duration=100)
    for tick in range(0, 201, 10):
        await engine.observe(
            Playback(track, True, tick % 100), monotonic=tick, wall_time=1_000 + tick
        )
    assert lastfm.scrobbles == [(track, 1_000), (track, 1_100)]
    assert queue.first() is None
    queue.close()


async def test_pending_repeat_listens_survive_restart_without_extra_queue_entries(
    tmp_path: Path,
) -> None:
    class UnavailableLastfm(FakeLastfm):
        async def scrobble(self, track: Track, started_at: int) -> None:
            raise LastfmError("Temporarily unavailable", retryable=True)

    database = tmp_path / "state.db"
    queue = ScrobbleQueue(database)
    engine = ScrobbleEngine(UnavailableLastfm(), queue)
    track = Track("Chelsea Wolfe", "Spun", duration=100)
    for tick in range(0, 191, 10):
        await engine.observe(
            Playback(track, True, tick % 100), monotonic=tick, wall_time=1_000 + tick
        )
    queue.close()

    lastfm = FakeLastfm()
    queue = ScrobbleQueue(database)
    engine = ScrobbleEngine(lastfm, queue)
    for _ in range(3):
        await engine.flush_one()
    assert lastfm.scrobbles == [(track, 1_000), (track, 1_100)]
    assert queue.first() is None
    queue.close()
