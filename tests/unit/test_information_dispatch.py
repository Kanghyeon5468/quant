import fcntl
from types import SimpleNamespace

from quantcore.information.background import trigger


def test_worker_dispatch_is_nonblocking_and_start_deduplicated(tmp_path, monkeypatch):
    calls = []

    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(pid=12345)

    monkeypatch.setattr("quantcore.information.background.subprocess.Popen", spawn)
    assert trigger(tmp_path)["status"] == "queued"
    assert trigger(tmp_path)["status"] == "starting"
    assert len(calls) == 1 and calls[0][1]["start_new_session"] is True


def test_running_collection_never_starts_another_process(tmp_path, monkeypatch):
    directory = tmp_path / "artifacts/information_worker"
    directory.mkdir(parents=True)

    def forbidden(*a, **k):
        raise AssertionError("another worker must not spawn")

    monkeypatch.setattr("quantcore.information.background.subprocess.Popen", forbidden)
    with (directory / "runner.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert trigger(tmp_path)["status"] == "running"
