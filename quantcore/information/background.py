"""Dispatch bounded information refreshes without holding the paper trading/risk lock."""

import fcntl
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from quantcore.core.files import atomic_json
from quantcore.information.store import now


def trigger(root, env_file=None):
    root = Path(root)
    directory = root / "artifacts/information_worker"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "dispatcher.lock").open("a") as dispatcher:
        try:
            fcntl.flock(dispatcher.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "running"}
        with (directory / "runner.lock").open("a") as worker:
            try:
                fcntl.flock(worker.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "running"}
            fcntl.flock(worker.fileno(), fcntl.LOCK_UN)
        state_file = directory / "state.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        kinds = ["financials", "institutions", "news", "earnings", "llm_analysis"]
        config = root / "configs/information.json"
        if config.exists() and json.loads(config.read_text()).get("macro_public"):
            kinds.append("macro")
        if config.exists() and json.loads(config.read_text()).get("crypto_public"):
            kinds.append("crypto")
        if all(
            k in state
            and pd.Timestamp(state[k].get("next_attempt_at", "1970-01-01T00:00Z"))
            > pd.Timestamp.now(tz="UTC")
            for k in kinds
        ):
            return {"status": "cached", "sources": {k: v.get("status") for k, v in state.items()}}
        dispatch_file = directory / "dispatch.json"
        previous = json.loads(dispatch_file.read_text()) if dispatch_file.exists() else {}
        if previous.get("started_at") and pd.Timestamp.now(tz="UTC") - pd.Timestamp(
            previous["started_at"]
        ) < pd.Timedelta(seconds=10):
            return {"status": "starting"}
        executable = root / ".venv/bin/python"
        argv = [
            str(executable) if executable.exists() else sys.executable,
            str(root / "scripts/collect_information.py"),
        ]
        if env_file:
            argv += ["--env-file", str(Path(env_file).resolve())]
        log_path = directory / "worker.log"
        with log_path.open("a") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen(
                argv, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True
            )
        metadata = {"status": "queued", "started_at": now(), "process_id": process.pid}
        atomic_json(dispatch_file, metadata)
        return metadata
