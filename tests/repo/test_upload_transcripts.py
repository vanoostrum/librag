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
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "upload_transcripts.py"
SETTINGS = ROOT / ".claude" / "settings.json"
SESSION = "0b1c2d3e-session"
SECRET = "sk-test-0123456789abcdef"  # noqa: S105 - a fake secret to redact.
KEY = {"type": "service_account", "client_email": "factory@example.iam"}
OPUS = "claude-opus"
SONNET = "claude-sonnet"

FAKE_GCLOUD = """#!/bin/sh
echo "$* token=${CLOUDSDK_AUTH_ACCESS_TOKEN:-none}" >> "$FAKE_GCLOUD_LOG"
if [ "$1" = "storage" ] && [ "$2" = "rsync" ]; then
  dest="$FAKE_BUCKET_ROOT/${4#gs://}"
  mkdir -p "$dest" && cp -R "$3"/. "$dest"/
fi
"""


def stamp(minute: int) -> str:
    """Return a transcript timestamp at a minute past 10:00."""
    return f"2026-11-02T10:{minute:02d}:00.000Z"


def reply(
    minute: int, message_id: str, model: str, tokens: int, *content: dict[str, Any]
) -> dict[str, Any]:
    """Return an assistant line with its token usage."""
    usage = {
        "input_tokens": tokens,
        "output_tokens": 1,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    return {
        "type": "assistant",
        "timestamp": stamp(minute),
        "message": {
            "id": message_id,
            "model": model,
            "usage": usage,
            "content": list(content),
        },
    }


def skill(name: str, args: str = "") -> dict[str, Any]:
    """Return a Skill tool call block."""
    return {
        "type": "tool_use",
        "id": f"call-{name}",
        "name": "Skill",
        "input": {"skill": name, "args": args},
    }


def write_jsonl(path: Path, lines: list[dict[str, Any]]) -> None:
    """Write transcript lines to a file."""
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), "utf-8")


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
    """Return a build session: build, review, and merge, with two subagents.

    Subagent a1 is linked to its `Agent` call. Subagent b2 is not, and wrote
    its first line during the review.
    """
    sessions = tmp_path / "sessions"
    main = sessions / f"{SESSION}.jsonl"
    subagents = sessions / SESSION / "subagents"
    subagents.mkdir(parents=True)
    agent_call = {
        "type": "tool_use",
        "id": "call-agent",
        "name": "Agent",
        "input": {"description": "app driver", "subagent_type": "general-purpose"},
    }
    write_jsonl(
        main,
        [
            {
                "type": "user",
                "timestamp": stamp(0),
                "message": {"content": f"key {SECRET}"},
            },
            # One reply written as two lines, each with the same usage.
            reply(1, "m1", SONNET, 100, {"type": "text", "text": "Building."}),
            reply(1, "m1", SONNET, 100, skill("factory-build", "LIBRAG-12")),
            reply(2, "m2", SONNET, 20, agent_call),
            {
                "type": "user",
                "timestamp": stamp(5),
                "toolUseResult": {"agentId": "a1"},
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "call-agent"}]
                },
            },
            reply(10, "m3", OPUS, 300, skill("factory-review", "LIBRAG-12")),
            reply(20, "m4", OPUS, 7, skill("factory-merge")),
            reply(21, "m5", OPUS, 5, {"type": "text", "text": "Merged."}),
        ],
    )
    write_jsonl(subagents / "agent-a1.jsonl", [reply(3, "s1", SONNET, 40)])
    write_jsonl(subagents / "agent-b2.jsonl", [reply(12, "s2", OPUS, 50)])
    return main


def fake_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Return an environment whose `gcloud` is the fake one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(FAKE_GCLOUD, encoding="utf-8")
    gcloud.chmod(0o755)
    temp = tmp_path / "tmp"
    temp.mkdir(exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("FACTORY_GCS_")
    }
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
        TMPDIR=str(temp),
        FAKE_GCLOUD_LOG=str(tmp_path / "gcloud.log"),
        FAKE_BUCKET_ROOT=str(tmp_path / "gcs"),
        OPENAI_API_KEY=SECRET,
        CLOUDSDK_AUTH_ACCESS_TOKEN="proxy-injected",  # noqa: S106 - as in the sandbox.
        **extra,
    )
    return env


def configured_env(tmp_path: Path, key: str = json.dumps(KEY)) -> dict[str, str]:
    """Return an environment with a bucket and a service account key."""
    return fake_env(tmp_path, FACTORY_GCS_BUCKET="factory-logs", FACTORY_GCS_KEY=key)


def run_hook(
    env: dict[str, str], transcript: Path, cwd: Path, event: str = "Stop"
) -> None:
    """Run the hook as Claude Code does."""
    payload = {
        "session_id": SESSION,
        "transcript_path": str(transcript),
        "cwd": str(cwd),
        "hook_event_name": event,
    }
    subprocess.run(  # noqa: S603
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        env=env,
        check=True,
        timeout=10,
    )


def wait_for_uploads(tmp_path: Path, count: int) -> None:
    """Wait until the background process has logged `count` uploads."""
    upload_log = tmp_path / "tmp" / "factory-transcripts" / "upload.log"
    deadline = time.monotonic() + 20
    while True:
        text = upload_log.read_text("utf-8") if upload_log.exists() else ""
        if text.count(" uploaded ") >= count:
            return
        if " failed " in text or time.monotonic() > deadline:
            pytest.fail(f"the upload did not finish: {text!r}")
        time.sleep(0.1)


def session_folder(tmp_path: Path) -> Path:
    """Return the session's folder in the fake bucket."""
    return tmp_path / "gcs" / "factory-logs" / "librag" / "sessions" / SESSION


def metadata(tmp_path: Path) -> dict[str, Any]:
    """Return the uploaded metadata of the session."""
    return json.loads((session_folder(tmp_path) / "metadata.json").read_text("utf-8"))


def tokens(model: str, input_tokens: int, replies: int) -> dict[str, dict[str, int]]:
    """Return the expected token totals of one model."""
    return {
        model: {
            "input_tokens": input_tokens,
            "output_tokens": replies,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    }


def test_uploads_the_session_transcripts(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """The bucket gets the gzipped transcripts, with secrets redacted."""
    run_hook(configured_env(tmp_path), transcript, project)
    wait_for_uploads(tmp_path, 1)

    folder = session_folder(tmp_path)
    main = gzip.decompress((folder / "session.jsonl.gz").read_bytes()).decode()
    subagent = gzip.decompress(
        (folder / "subagents" / "agent-a1.jsonl.gz").read_bytes()
    )

    assert "key [redacted:OPENAI_API_KEY]" in main
    assert SECRET not in main
    assert (
        subagent
        == (transcript.parent / SESSION / "subagents" / "agent-a1.jsonl").read_bytes()
    )
    data = metadata(tmp_path)
    assert data["repo"] == "librag"
    assert data["branch"] == "librag-12/version-endpoint"
    assert data["session_id"] == SESSION
    assert data["tickets"] == ["LIBRAG-12"]
    assert data["event"] == "Stop"


def test_splits_the_session_into_factory_steps(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """Each factory Skill call starts a segment with its ticket, times, and tokens."""
    run_hook(configured_env(tmp_path), transcript, project)
    wait_for_uploads(tmp_path, 1)

    build, review, merge = metadata(tmp_path)["segments"]

    assert (build["step"], build["ticket"]) == ("build", "LIBRAG-12")
    assert (build["started_at"], build["ended_at"]) == (stamp(1), stamp(5))
    assert build["tokens"] == tokens(SONNET, 120, 2)
    assert (review["step"], review["ticket"]) == ("review", "LIBRAG-12")
    assert review["tokens"] == tokens(OPUS, 300, 1)
    assert (merge["step"], merge["ticket"]) == ("merge", "LIBRAG-12")
    assert (merge["started_at"], merge["ended_at"]) == (stamp(20), stamp(21))
    assert merge["tokens"] == tokens(OPUS, 12, 2)


def test_assigns_subagents_to_their_step(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """A subagent goes to the step of its `Agent` call, or else of its start time."""
    run_hook(configured_env(tmp_path), transcript, project)
    wait_for_uploads(tmp_path, 1)

    build, review, merge = metadata(tmp_path)["segments"]

    assert build["subagents"] == [
        {
            "agent_id": "a1",
            "role": "app driver",
            "started_at": stamp(3),
            "ended_at": stamp(3),
            "tokens": tokens(SONNET, 40, 1),
        }
    ]
    assert [s["agent_id"] for s in review["subagents"]] == ["b2"]
    assert review["subagents"][0]["role"] is None
    assert review["subagents"][0]["tokens"] == tokens(OPUS, 50, 1)
    assert merge["subagents"] == []


def test_session_without_a_ticket(tmp_path: Path, project: Path) -> None:
    """Outside the factory, the session is one segment without a step or ticket."""
    subprocess.run(  # noqa: S603
        ["git", "-C", str(project), "checkout", "-q", "-b", "claude/thread"],  # noqa: S607
        check=True,
    )
    plain = tmp_path / "plain.jsonl"
    write_jsonl(plain, [reply(1, "m1", OPUS, 9, {"type": "text", "text": "Hi."})])
    run_hook(configured_env(tmp_path), plain, project)
    wait_for_uploads(tmp_path, 1)

    data = metadata(tmp_path)
    assert data["tickets"] == []
    assert [(s["step"], s["ticket"]) for s in data["segments"]] == [(None, None)]


def test_skips_a_stop_soon_after_an_upload(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """A Stop within the interval does not upload; a SubagentStop does."""
    env = configured_env(tmp_path)
    run_hook(env, transcript, project)
    wait_for_uploads(tmp_path, 1)

    run_hook(env, transcript, project, "Stop")
    run_hook(env, transcript, project, "SubagentStop")
    wait_for_uploads(tmp_path, 2)
    time.sleep(1)

    upload_log = tmp_path / "tmp" / "factory-transcripts" / "upload.log"
    uploads = upload_log.read_text("utf-8").count(" uploaded ")
    assert uploads == len(["first Stop", "SubagentStop"])
    assert metadata(tmp_path)["event"] == "SubagentStop"


def test_stop_uploads_again_after_the_interval(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """With an interval of 0, every Stop uploads."""
    env = configured_env(tmp_path)
    env["FACTORY_GCS_STOP_INTERVAL"] = "0"
    run_hook(env, transcript, project)
    wait_for_uploads(tmp_path, 1)
    run_hook(env, transcript, project)
    wait_for_uploads(tmp_path, 2)


def test_unchanged_files_keep_the_same_bytes(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """Two uploads of an unchanged transcript write identical gzip files."""
    env = configured_env(tmp_path)
    run_hook(env, transcript, project, "SubagentStop")
    wait_for_uploads(tmp_path, 1)
    first = (session_folder(tmp_path) / "session.jsonl.gz").read_bytes()
    time.sleep(1.1)
    run_hook(env, transcript, project, "SubagentStop")
    wait_for_uploads(tmp_path, 2)

    assert (session_folder(tmp_path) / "session.jsonl.gz").read_bytes() == first


def test_accepts_a_base64_key(tmp_path: Path, project: Path, transcript: Path) -> None:
    """The key can be base64, which fits in a one-line environment variable."""
    key = base64.b64encode(json.dumps(KEY).encode()).decode()
    run_hook(configured_env(tmp_path, key), transcript, project)
    wait_for_uploads(tmp_path, 1)

    log = (tmp_path / "gcloud.log").read_text(encoding="utf-8")
    assert "auth activate-service-account" in log


def test_ignores_the_sandbox_access_token(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """The upload runs as the service account, not with the sandbox token."""
    run_hook(configured_env(tmp_path), transcript, project)
    wait_for_uploads(tmp_path, 1)

    log = (tmp_path / "gcloud.log").read_text(encoding="utf-8").splitlines()
    assert log
    assert all(line.endswith("token=none") for line in log)


def test_uses_the_proxy_token_without_a_key(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """In a cloud session without a key, gcloud uses the token the proxy adds."""
    env = fake_env(tmp_path, FACTORY_GCS_BUCKET="factory-logs")
    run_hook(env, transcript, project)
    wait_for_uploads(tmp_path, 1)

    log = (tmp_path / "gcloud.log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1
    assert log[0].startswith("storage rsync ")
    assert log[0].endswith("token=proxy-injected")
    assert (session_folder(tmp_path) / "metadata.json").is_file()


def test_does_nothing_without_a_way_to_sign_in(
    tmp_path: Path, project: Path, transcript: Path
) -> None:
    """With a bucket but no key and no proxy token, the hook calls no Google tool."""
    env = fake_env(tmp_path, FACTORY_GCS_BUCKET="factory-logs")
    del env["CLOUDSDK_AUTH_ACCESS_TOKEN"]
    run_hook(env, transcript, project)
    time.sleep(1)

    assert not (tmp_path / "gcloud.log").exists()


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


def test_settings_name_the_bucket() -> None:
    """Every session gets the bucket name; the key stays out of the repo."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert settings["env"]["FACTORY_GCS_BUCKET"] == "sous-factory-transcripts"
    assert "FACTORY_GCS_KEY" not in settings["env"]
