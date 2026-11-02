# Copyright (C) 2026 Theo van Oostrum
"""Stop, SubagentStop, and SessionEnd hook: copy transcripts to Google Cloud Storage.

Proof of concept for the factory dashboard. The hook does nothing unless
`FACTORY_GCS_BUCKET` and `FACTORY_GCS_KEY` are set. `FACTORY_GCS_KEY` holds a
service account key, as JSON or base64 JSON.

The hook returns at once and uploads in a background process, so a turn does
not wait for Google Cloud. Each upload writes the whole session to the same
folder, so the bucket always holds the latest state:

    gs://<bucket>/<repo>/sessions/<session id>/
        session.jsonl.gz
        subagents/<agent>.jsonl.gz
        metadata.json

`metadata.json` splits the session into segments. Each `factory-*` Skill call
starts a segment. A segment has its step, its ticket, its start and end time,
its tokens per model, and its subagents with their own tokens.

- The ticket of a segment comes from the Skill arguments, such as `LIBRAG-12`,
  or else from the branch name, such as `librag-12/version-endpoint`.
- A subagent belongs to the segment whose `Agent` call started it. When the
  transcript does not link the two, it belongs to the segment that was running
  when the subagent wrote its first line.
- A Stop upload is skipped when the last upload of the session is less than
  `FACTORY_GCS_STOP_INTERVAL` seconds old (default 300). SubagentStop and
  SessionEnd always upload.
- One upload per session runs at a time. The next one waits for it.
- The gzip files have a fixed timestamp, so an unchanged file has the same
  bytes, and `gcloud storage rsync` skips it.

Secret environment values are replaced before upload. The background process
logs each upload, or its error, to `factory-transcripts/upload.log` in the
temp folder.

Setup for cloud sessions: allow `storage.googleapis.com` and
`oauth2.googleapis.com` in the environment's network access, and set both
variables in the environment. The key needs only the Storage Object User role
on the bucket.
"""

import base64
import binascii
import contextlib
import fcntl
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUCKET_ENV = "FACTORY_GCS_BUCKET"
KEY_ENV = "FACTORY_GCS_KEY"
INTERVAL_ENV = "FACTORY_GCS_STOP_INTERVAL"
DEFAULT_STOP_INTERVAL = 300.0
UPLOAD_FLAG = "--upload"
TICKET_BRANCH = re.compile(r"^([a-z]+)-(\d+)/")
TICKET_KEY = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
FACTORY_SKILL = re.compile(r"^factory[-:]([a-z]+)$")
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
MIN_SECRET_LENGTH = 8
AGENT_TOOLS = {"Agent", "Task"}
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

Tokens = dict[str, dict[str, int]]


def state_dir() -> Path:
    """Return the folder for the log, the locks, and the last upload times."""
    folder = Path(tempfile.gettempdir()) / "factory-transcripts"
    folder.mkdir(exist_ok=True)
    return folder


def git(cwd: str, *args: str) -> str:
    """Return the output of a git command, or "" when it fails."""
    result = subprocess.run(  # noqa: S603
        ["git", "-C", cwd, *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def ticket_of(branch: str) -> str | None:
    """Return the ticket key of a factory branch, or None."""
    match = TICKET_BRANCH.match(branch)
    if match is None:
        return None
    return f"{match.group(1).upper()}-{match.group(2)}"


def secrets() -> dict[str, str]:
    """Return the environment values that look like secrets, by name."""
    return {
        name: value
        for name, value in os.environ.items()
        if SECRET_NAME.search(name) and len(value) >= MIN_SECRET_LENGTH
    }


def redact(text: str, values: dict[str, str]) -> str:
    """Replace each secret value in `text` with its variable name."""
    for name, value in sorted(values.items(), key=lambda item: -len(item[1])):
        text = text.replace(value, f"[redacted:{name}]")
    return text


def key_json(raw: str) -> str:
    """Return the service account key as JSON, decoding base64 if needed."""
    if raw.lstrip().startswith("{"):
        return raw
    try:
        return base64.b64decode(raw, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return raw


def transcripts(transcript: Path) -> dict[str, Path]:
    """Return the session transcript and its subagent transcripts, by upload name."""
    found = {"session.jsonl": transcript} if transcript.is_file() else {}
    folder = transcript.with_suffix("")
    if folder.is_dir():
        for path in sorted(folder.rglob("*.jsonl")):
            found[str(path.relative_to(folder))] = path
    return found


def entries(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the JSON objects of a transcript, skipping broken lines."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the content blocks of a transcript entry."""
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def add_usage(tokens: Tokens, model: str, usage: dict[str, Any]) -> None:
    """Add one reply's token usage to the totals of its model."""
    totals = tokens.setdefault(model, dict.fromkeys(USAGE_FIELDS, 0))
    for name in USAGE_FIELDS:
        value = usage.get(name)
        if isinstance(value, int):
            totals[name] += value


def usage_by_reply(path: Path) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Return each reply's timestamp, model, and usage, by message id.

    Claude Code writes one reply as several lines, one per content block, and
    repeats the usage on each. Keying by message id counts each reply once.
    """
    replies: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for number, entry in enumerate(entries(path)):
        message = entry.get("message") or {}
        usage = message.get("usage")
        if entry.get("type") != "assistant" or not isinstance(usage, dict):
            continue
        key = message.get("id") or f"line-{number}"
        replies[key] = (entry.get("timestamp") or "", message.get("model") or "", usage)
    return replies


@dataclass
class Subagent:
    """A subagent transcript and its totals."""

    agent_id: str
    role: str | None
    started_at: str | None
    ended_at: str | None
    tokens: Tokens = field(default_factory=dict)


@dataclass
class Segment:
    """The part of a session that one factory step ran."""

    step: str | None
    ticket: str | None
    started_at: str | None
    ended_at: str | None = None
    tokens: Tokens = field(default_factory=dict)
    subagents: list[Subagent] = field(default_factory=list)
    agent_calls: dict[str, str | None] = field(default_factory=dict)


def segment_starts(path: Path, branch_ticket: str | None) -> list[Segment]:
    """Return the segments of the main transcript, with their `Agent` calls."""
    segments = [Segment(step=None, ticket=branch_ticket, started_at=None)]
    for entry in entries(path):
        stamp = entry.get("timestamp")
        for block in blocks(entry):
            if block.get("type") != "tool_use":
                continue
            tool_input = block.get("input") or {}
            if block.get("name") == "Skill":
                match = FACTORY_SKILL.match(str(tool_input.get("skill") or ""))
                if match:
                    found = TICKET_KEY.search(str(tool_input.get("args") or ""))
                    ticket = found.group(0) if found else branch_ticket
                    segments.append(Segment(match.group(1), ticket, stamp, stamp))
            elif block.get("name") in AGENT_TOOLS:
                role = tool_input.get("description") or tool_input.get("subagent_type")
                segments[-1].agent_calls[str(block.get("id"))] = role
        if stamp:
            segments[-1].started_at = segments[-1].started_at or stamp
            segments[-1].ended_at = stamp
    return segments


def agent_links(path: Path) -> dict[str, str]:
    """Return the `Agent` call id that started each subagent, by agent id."""
    links: dict[str, str] = {}
    for entry in entries(path):
        result = entry.get("toolUseResult")
        agent_id = result.get("agentId") if isinstance(result, dict) else None
        if not agent_id:
            continue
        for block in blocks(entry):
            if block.get("type") == "tool_result" and block.get("tool_use_id"):
                links[str(agent_id)] = str(block["tool_use_id"])
    return links


def segment_at(segments: list[Segment], stamp: str | None) -> Segment:
    """Return the segment that was running at `stamp`."""
    current = segments[0]
    for segment in segments:
        start = segment.started_at
        if stamp is not None and start is not None and start <= stamp:
            current = segment
    return current


def segment_session(transcript: Path, branch_ticket: str | None) -> list[Segment]:
    """Split a session into segments and add the tokens of each."""
    segments = segment_starts(transcript, branch_ticket)
    for stamp, model, usage in usage_by_reply(transcript).values():
        add_usage(segment_at(segments, stamp).tokens, model, usage)
    links = agent_links(transcript)
    folder = transcript.with_suffix("")
    for path in sorted(folder.rglob("agent-*.jsonl")) if folder.is_dir() else []:
        agent_id = path.stem.removeprefix("agent-")
        replies = list(usage_by_reply(path).values())
        stamps = sorted(s for s in (e.get("timestamp") for e in entries(path)) if s)
        call = links.get(agent_id)
        owner = next((s for s in segments if call in s.agent_calls), None)
        if owner is None:
            owner = segment_at(segments, stamps[0] if stamps else None)
        subagent = Subagent(
            agent_id=agent_id,
            role=owner.agent_calls.get(call) if call is not None else None,
            started_at=stamps[0] if stamps else None,
            ended_at=stamps[-1] if stamps else None,
        )
        for _, model, usage in replies:
            add_usage(subagent.tokens, model, usage)
        owner.subagents.append(subagent)
    return [s for s in segments if s.step is not None or s.tokens or s.subagents]


def segment_json(segment: Segment) -> dict[str, Any]:
    """Return a segment as it goes into `metadata.json`."""
    return {
        "step": segment.step,
        "ticket": segment.ticket,
        "started_at": segment.started_at,
        "ended_at": segment.ended_at,
        "tokens": segment.tokens,
        "subagents": [
            {
                "agent_id": subagent.agent_id,
                "role": subagent.role,
                "started_at": subagent.started_at,
                "ended_at": subagent.ended_at,
                "tokens": subagent.tokens,
            }
            for subagent in segment.subagents
        ],
    }


def stage(event: dict[str, Any], out: Path) -> str:
    """Write the gzipped transcripts and metadata to `out`. Return the prefix."""
    cwd = event.get("cwd") or str(Path.cwd())
    repo = Path(git(cwd, "rev-parse", "--show-toplevel") or cwd).name
    branch = git(cwd, "branch", "--show-current")
    session = event.get("session_id") or "unknown-session"
    transcript = Path(event.get("transcript_path") or "")
    values = secrets()
    for name, path in transcripts(transcript).items():
        target = out / f"{name}.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8", errors="replace")
        target.write_bytes(gzip.compress(redact(text, values).encode(), mtime=0))
    segments = (
        segment_session(transcript, ticket_of(branch)) if transcript.is_file() else []
    )
    metadata = {
        "repo": repo,
        "branch": branch,
        "session_id": session,
        "tickets": sorted({s.ticket for s in segments if s.ticket is not None}),
        "segments": [segment_json(segment) for segment in segments],
        "event": event.get("hook_event_name"),
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return f"{repo}/sessions/{session}"


def gcloud(config: Path, *args: str) -> None:
    """Run gcloud as the service account, with its own config folder.

    The own folder keeps the user's gcloud login as it is. The cloud sandbox
    sets `CLOUDSDK_AUTH_ACCESS_TOKEN`, which would override the service account.
    """
    env = {
        name: value
        for name, value in os.environ.items()
        if name != "CLOUDSDK_AUTH_ACCESS_TOKEN"
    }
    env["CLOUDSDK_CONFIG"] = str(config)
    subprocess.run(  # noqa: S603
        ["gcloud", *args, "--quiet"],  # noqa: S607
        env=env,
        check=True,
        capture_output=True,
    )


def upload(event: dict[str, Any]) -> None:
    """Stage the session and copy it to the bucket."""
    bucket = os.environ[BUCKET_ENV]
    with tempfile.TemporaryDirectory(prefix="factory-transcripts-") as tmp:
        work = Path(tmp)
        key = work / "key.json"
        key.write_text(key_json(os.environ[KEY_ENV]), encoding="utf-8")
        key.chmod(0o600)
        out = work / "out"
        out.mkdir()
        prefix = stage(event, out)
        config = work / "gcloud"
        gcloud(config, "auth", "activate-service-account", f"--key-file={key}")
        gcloud(
            config,
            "storage",
            "rsync",
            str(out),
            f"gs://{bucket}/{prefix}",
            "--recursive",
        )


def log(message: str) -> None:
    """Append a line to the upload log."""
    with (
        contextlib.suppress(OSError),
        (state_dir() / "upload.log").open("a", encoding="utf-8") as file,
    ):
        file.write(f"{datetime.now(UTC).isoformat()} {message}\n")


def session_file(session: str, suffix: str) -> Path:
    """Return a state file of one session."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session)
    return state_dir() / f"{safe}.{suffix}"


def recently_uploaded(session: str) -> bool:
    """Return whether the session's last upload is newer than the Stop interval."""
    try:
        interval = float(os.environ.get(INTERVAL_ENV, "") or DEFAULT_STOP_INTERVAL)
        last = float(session_file(session, "last").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return time.time() - last < interval


def upload_locked(event: dict[str, Any]) -> None:
    """Upload under the session's lock, and log the result."""
    session = str(event.get("session_id") or "unknown-session")
    with session_file(session, "lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            upload(event)
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", b"") or b""
            log(f"failed {session}: {error} {detail.decode()[-500:]}")
            return
        session_file(session, "last").write_text(str(time.time()), encoding="utf-8")
        log(f"uploaded {session} ({event.get('hook_event_name')})")


def main() -> None:
    """Start a background upload, or run it when called with the upload flag."""
    if not (os.environ.get(BUCKET_ENV, "") and os.environ.get(KEY_ENV, "")):
        return
    if sys.argv[1:2] == [UPLOAD_FLAG]:
        upload_locked(json.loads(sys.argv[2]))
        return
    event = json.load(sys.stdin)
    session = str(event.get("session_id") or "unknown-session")
    if event.get("hook_event_name") == "Stop" and recently_uploaded(session):
        return
    subprocess.Popen(  # noqa: S603
        [sys.executable, __file__, UPLOAD_FLAG, json.dumps(event)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


if __name__ == "__main__":
    main()
