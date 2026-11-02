# Copyright (C) 2026 Theo van Oostrum
"""The upload hook copies a session's transcripts to Google Cloud Storage.

A fake `gcloud` on `PATH` stands in for Google Cloud. Its `storage rsync`
copies the folder into a local "bucket" folder, so the tests can read what
would land in the bucket.
"""

import base64
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "upload_transcripts.py"
SETTINGS = ROOT / ".claude" / "settings.json"
SESSION = "0b1c2d3e-session"
SECRET = "sk-test-0123456789abcdef"  # noqa: S105 - a fake secret to redact.
KEY = {"type": "service_account", "client_email": "factory@example.iam"}

FAKE_GCLOUD = """#!/bin/sh
echo "$* token=${CLOUDSDK_AUTH_ACCESS_TOKEN:-none}" >> "$FAKE_GCLOUD_LOG"
if [ "$1" = "storage" ] && [ "$2" = "rsync" ]; then
  dest="$FAKE_BUCKET_ROOT/${4#gs://}"
  mkdir -p "$dest" && cp -R "$3"/. "$dest"/
  touch "$FAKE_GCLOUD_LOG.done"
fi
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Return a git checkout on a factory branch."""
    repo = tmp_path / "librag"
    repo.mkdir()
    subprocess.run(  # noqa: S603
        ["git", "init", "-q", "-b", "librag-12/version-endpoint", str(repo)],  # noqa: S607
        check=True,
    )
    return repo


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    """Return a session transcript with one subagent transcript next to it."""
    sessions = tmp_path / "sessions"
    main = sessions / f"{SESSION}.jsonl"
    subagents = sessions / SESSION / "subagents"
    subagents.mkdir(parents=True)
    main.write_text(
        json.dumps({"type": "user", "message": {"content": f"key {SECRET}"}}) + "\n",
        encoding="utf-8",
    )
    (subagents / "agent-a1.jsonl").write_text('{"type": "assistant"}\n')
    return main


def fake_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Return an environment whose `gcloud` is the fake one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(FAKE_GCLOUD, encoding="utf-8")
    gcloud.chmod(0o755)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("FACTORY_GCS_")
    }
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
        FAKE_GCLOUD_LOG=str(tmp_path / "gcloud.log"),
        FAKE_BUCKET_ROOT=str(tmp_path / "gcs"),
        OPENAI_API_KEY=SECRET,
        CLOUDSDK_AUTH_ACCESS_TOKEN="proxy-injected",  # noqa: S106 - as in the sandbox.
        **extra,
    )
    return env


def run_hook(env: dict[str, str], transcript: Path, cwd: Path) -> None:
    """Run the hook as Claude Code does after a turn."""
    event = {
        "session_id": SESSION,
        "transcript_path": str(transcript),
        "cwd": str(cwd),
        "hook_event_name": "Stop",
    }
    subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        env=env,
        check=True,
        timeout=10,
    )


def wait_for(path: Path) -> None:
    """Wait until the background upload has written `path`."""
    deadline = time.monotonic() + 20
    while not path.exists():
        if time.monotonic() > deadline:
            pytest.fail(f"the upload did not finish: {path} is missing")
        time.sleep(0.1)


def configured_env(tmp_path: Path, key: str) -> dict[str, str]:
    """Return an environment with a bucket and a service account key."""
    return fake_env(tmp_path, FACTORY_GCS_BUCKET="factory-logs", FACTORY_GCS_KEY=key)


def test_uploads_the_session_under_its_ticket(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """The bucket gets the gzipped transcripts and metadata for the ticket."""
    run_hook(configured_env(tmp_path, json.dumps(KEY)), transcript, project)
    wait_for(tmp_path / "gcloud.log.done")

    folder = tmp_path / "gcs" / "factory-logs" / "librag" / "LIBRAG-12" / SESSION
    main = gzip.decompress((folder / "session.jsonl.gz").read_bytes()).decode()
    subagent = folder / "subagents" / "agent-a1.jsonl.gz"
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))

    assert "key [redacted:OPENAI_API_KEY]" in main
    assert SECRET not in main
    assert gzip.decompress(subagent.read_bytes()) == b'{"type": "assistant"}\n'
    assert metadata["ticket"] == "LIBRAG-12"
    assert metadata["branch"] == "librag-12/version-endpoint"
    assert metadata["session_id"] == SESSION
    assert metadata["event"] == "Stop"


def test_accepts_a_base64_key(tmp_path: Path, project: Path, transcript: Path) -> None:
    """The key can be base64, which fits in a one-line environment variable."""
    key = base64.b64encode(json.dumps(KEY).encode()).decode()
    run_hook(configured_env(tmp_path, key), transcript, project)
    wait_for(tmp_path / "gcloud.log.done")

    log = (tmp_path / "gcloud.log").read_text(encoding="utf-8")
    assert "auth activate-service-account" in log


def test_ignores_the_sandbox_access_token(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """The upload runs as the service account, not with the sandbox token."""
    run_hook(configured_env(tmp_path, json.dumps(KEY)), transcript, project)
    wait_for(tmp_path / "gcloud.log.done")

    log = (tmp_path / "gcloud.log").read_text(encoding="utf-8").splitlines()
    assert log
    assert all(line.endswith("token=none") for line in log)


def test_session_without_a_ticket_branch(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """A branch without a ticket key uploads under `no-ticket`."""
    subprocess.run(  # noqa: S603
        ["git", "-C", str(project), "checkout", "-q", "-b", "claude/thread"],  # noqa: S607
        check=True,
    )
    run_hook(configured_env(tmp_path, json.dumps(KEY)), transcript, project)
    wait_for(tmp_path / "gcloud.log.done")

    assert (
        tmp_path / "gcs" / "factory-logs" / "librag" / "no-ticket" / SESSION
    ).is_dir()


def test_does_nothing_without_a_bucket(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """Without the environment variables, the hook calls no Google tool."""
    run_hook(fake_env(tmp_path), transcript, project)
    time.sleep(1)

    assert not (tmp_path / "gcloud.log").exists()


@pytest.mark.parametrize("event", ["Stop", "SubagentStop", "SessionEnd"])
def test_settings_run_the_hook(event: str) -> None:
    """Claude Code runs the hook after each turn, each subagent, and at the end."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    commands = [
        hook["command"] for group in settings["hooks"][event] for hook in group["hooks"]
    ]
    assert any("upload_transcripts.py" in command for command in commands)
