from pathlib import Path

from eversolo_scrobbler.engine import ScrobbleEngine
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
    await engine.observe(Playback(track, True, 50), monotonic=60, wall_time=1_060)
    assert len(lastfm.now) == 2
    assert [(item[0].title, item[1]) for item in lastfm.scrobbles] == [("Title", 1_000)]


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


async def test_successful_song_is_never_scrobbled_twice_even_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    lastfm = FakeLastfm()
    first_queue = ScrobbleQueue(database)
    first = ScrobbleEngine(lastfm, first_queue)
    track = Track("King Gizzard & The Lizard Wizard", "Uqt", "Album One", duration=100)
    await first.observe(Playback(track, True, 0), monotonic=0, wall_time=1_000)
    await first.observe(Playback(track, True, 25), monotonic=25, wall_time=1_025)
    await first.observe(Playback(track, True, 50), monotonic=50, wall_time=1_050)
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
        ("King Gizzard & The Lizard Wizard", "Uqt")
    ]
    assert second_queue.first() is None
