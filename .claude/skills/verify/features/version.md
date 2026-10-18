# Version

A client that calls `/version` gets the installed LibRag version as JSON. The value matches `version` in `pyproject.toml`.

## Sub-features

- `version-json` returns 200 with `{"version":"<version>"}`.
- `version-matches` has the same value as `pyproject.toml`.

## How to get to it (user POV)

- Send `GET /version`.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.

- **Read the expected value.** Run `sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -1`. Note the value, for example `0.1.0`.
- **Call version.** Run `$V get version /version`. Status is `200` and the body is exactly `{"version":"<that value>"}`.
- **Check the type.** Read `.verify/$LIBRAG_VERIFY_RUN/evidence/version/version.headers`. It has `content-type: application/json`.

## Gotchas

- The route reads the installed package metadata, not `pyproject.toml` itself. After a version bump, `launch` runs `uv sync`, which updates it. A server started before the bump shows the old value; `doctor` catches that.
