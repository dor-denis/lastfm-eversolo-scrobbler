from eversolo_scrobbler.eversolo import parse_playback


def test_internal_player() -> None:
    result = parse_playback(
        {
            "state": 3,
            "playType": 5,
            "duration": 241999,
            "position": 12000,
            "playingMusic": {"artist": "Björk", "title": "Jóga", "album": "Homogenic"},
        }
    )
    assert result.playing
    assert result.position == 12
    assert result.track is not None
    assert result.track.duration == 241
    assert result.track.artist == "Björk"


def test_spotify_connect() -> None:
    result = parse_playback(
        {
            "state": "4",
            "playType": 6,
            "duration": 100000,
            "everSoloPlayInfo": {
                "everSoloPlayAudioInfo": {
                    "artistName": "Artist",
                    "songName": "Song",
                    "albumName": "Album",
                }
            },
        }
    )
    assert not result.playing
    assert result.track is not None
    assert result.track.title == "Song"


def test_missing_metadata_is_not_a_track() -> None:
    assert parse_playback({"state": 3, "playType": 5}).track is None


def test_apple_music_prefers_live_external_metadata_over_stale_internal_track() -> None:
    result = parse_playback(
        {
            "state": 3,
            "playType": 8,
            "duration": 257000,
            "position": 147087,
            "playingMusic": {"artist": "Garbage", "title": "Milk"},
            "everSoloPlayInfo": {
                "everSoloPlayAudioInfo": {
                    "artistName": "Peter Gabriel",
                    "songName": "Kiss of Life",
                    "albumName": "Peter Gabriel 4: Security (Remastered)",
                }
            },
        }
    )
    assert result.track is not None
    assert result.track.artist == "Peter Gabriel"
    assert result.track.title == "Kiss of Life"


def test_apple_classical_never_falls_back_to_stale_internal_track() -> None:
    result = parse_playback(
        {
            "state": 3,
            "playType": 8,
            "duration": 3559677,
            "playingMusic": {"artist": "Garbage", "title": "Milk"},
            "everSoloPlayInfo": {
                "playTypePackageName": "com.apple.android.music.classical",
                "everSoloPlayAudioInfo": {
                    "artistName": "",
                    "songName": "Prelude",
                    "albumName": "The Story of Classical",
                },
            },
        }
    )
    assert result.track is None
    assert result.playing
