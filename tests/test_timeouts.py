import logging
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from eversolo_scrobbler import cli
from eversolo_scrobbler.engine import ScrobbleEngine
from eversolo_scrobbler.eversolo import EversoloClient, EversoloError
from eversolo_scrobbler.lastfm import LastfmClient, LastfmError
from eversolo_scrobbler.models import Track
from eversolo_scrobbler.storage import ScrobbleQueue


@pytest.fixture(params=[TimeoutError, aiohttp.ServerTimeoutError])
def timed_out_session(request):
    session = MagicMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(side_effect=request.param())
    session.get.return_value = context
    session.post.return_value = context
    return session


async def test_eversolo_timeout_is_a_recoverable_device_error(timed_out_session):
    device = EversoloClient("localhost", 9529, timed_out_session)
    with pytest.raises(EversoloError, match="Eversolo request timed out"):
        await device.playback()


async def test_lastfm_timeout_is_retryable(timed_out_session):
    client = LastfmClient("key", "secret", "session", timed_out_session)
    with pytest.raises(LastfmError, match="Last.fm request timed out") as error:
        await client.now_playing(Track("Artist", "Title"))
    assert error.value.retryable


async def test_scrobble_timeout_keeps_pending_submission(timed_out_session, tmp_path):
    client = LastfmClient("key", "secret", "session", timed_out_session)
    queue = ScrobbleQueue(tmp_path / "state.db")
    try:
        track = Track("Artist", "Title", duration=100)
        queue.add(track, 1000)
        pending = queue.first()
        await ScrobbleEngine(client, queue).flush_one()
        assert queue.first() == pending
    finally:
        queue.close()


def test_runtime_error_is_logged_without_argument_usage(monkeypatch, caplog, capsys):
    monkeypatch.setattr("sys.argv", ["eversolo-scrobbler"])
    monkeypatch.setattr(cli, "run", AsyncMock(side_effect=TimeoutError()))
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert "TimeoutError: operation failed" in caplog.text
    assert "usage:" not in capsys.readouterr().err
