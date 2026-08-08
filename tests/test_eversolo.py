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
