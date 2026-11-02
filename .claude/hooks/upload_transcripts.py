# Copyright (C) 2026 Theo van Oostrum
"""Stop, SubagentStop, and SessionEnd hook: copy transcripts to Google Cloud Storage.

Proof of concept for the factory dashboard. The hook does nothing unless
`FACTORY_GCS_BUCKET` and `FACTORY_GCS_KEY` are set. `FACTORY_GCS_KEY` holds a
service account key, as JSON or base64 JSON.

The hook returns at once and uploads in a background process, so a turn does
not wait for Google Cloud. Each run uploads the whole session again to the
same folder, so the bucket always holds the latest state:

    gs://<bucket>/<repo>/<ticket>/<session id>/
        session.jsonl.gz
        subagents/<agent>.jsonl.gz
        metadata.json

The ticket comes from the branch name, such as `librag-12/version-endpoint`.
Secret environment values are replaced before upload. The background process
logs each upload, or its error, to `factory-transcripts.log` in the temp folder.

Setup for cloud sessions: allow `storage.googleapis.com` and
`oauth2.googleapis.com` in the environment's network access, and set both
variables in the environment. The key needs only the Storage Object User role
on the bucket.
"""

import base64
import binascii
import contextlib
import gzip
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUCKET_ENV = "FACTORY_GCS_BUCKET"
KEY_ENV = "FACTORY_GCS_KEY"
UPLOAD_FLAG = "--upload"
LOG = Path(tempfile.gettempdir()) / "factory-transcripts.log"
TICKET_BRANCH = re.compile(r"^([a-z]+)-(\d+)/")
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
MIN_SECRET_LENGTH = 8


def git(cwd: str, *args: str) -> str:
    """Return the output of a git command, or "" when it fails."""
    result = subprocess.run(  # noqa: S603
        ["git", "-C", cwd, *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def ticket_of(branch: str) -> str:
    """Return the ticket key of a factory branch, or `no-ticket`."""
    match = TICKET_BRANCH.match(branch)
    if match is None:
        return "no-ticket"
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


def stage(event: dict[str, Any], out: Path) -> str:
    """Write the gzipped transcripts and metadata to `out`. Return the prefix."""
    cwd = event.get("cwd") or str(Path.cwd())
    top = git(cwd, "rev-parse", "--show-toplevel") or cwd
    branch = git(cwd, "branch", "--show-current")
    ticket = ticket_of(branch)
    session = event.get("session_id") or "unknown-session"
    values = secrets()
    for name, path in transcripts(Path(event.get("transcript_path") or "")).items():
        target = out / f"{name}.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8", errors="replace")
        target.write_bytes(gzip.compress(redact(text, values).encode()))
    metadata = {
        "repo": Path(top).name,
        "branch": branch,
        "ticket": ticket,
        "session_id": session,
        "event": event.get("hook_event_name"),
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return f"{Path(top).name}/{ticket}/{session}"


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
    with contextlib.suppress(OSError), LOG.open("a", encoding="utf-8") as file:
        file.write(f"{datetime.now(UTC).isoformat()} {message}\n")


def main() -> None:
    """Start a background upload, or run it when called with the upload flag."""
    if not (os.environ.get(BUCKET_ENV, "") and os.environ.get(KEY_ENV, "")):
        return
    if sys.argv[1:2] == [UPLOAD_FLAG]:
        event = json.loads(sys.argv[2])
        try:
            upload(event)
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", b"") or b""
            log(f"failed {event.get('session_id')}: {error} {detail.decode()[-500:]}")
        else:
            log(f"uploaded {event.get('session_id')}")
        return
    event = json.load(sys.stdin)
    subprocess.Popen(  # noqa: S603
        [sys.executable, __file__, UPLOAD_FLAG, json.dumps(event)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


if __name__ == "__main__":
    main()
