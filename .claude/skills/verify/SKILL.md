---
name: verify
description: Drive the running LibRag FastAPI app over HTTP and capture evidence that a route behaves as specified. Use to prove a change in the real app (homepage, /health, /version, disabled API docs), not just in tests. For lint, type check, and tests, use project-verify.
---

# Verify LibRag in the running app

LibRag is an HTTP service. The user surface is its routes: `/` (HTML homepage), `/health`, and `/version`. The API docs (`/docs`, `/redoc`, `/openapi.json`) are off on purpose. There is no UI framework, auth, database, or seed data. The driver is `curl`, wrapped by one helper script.

`project-verify` runs ruff, ty, and pytest, the same as CI. This skill is the other half: it starts a real server and checks what a client sees.

All commands run from the repo root. The helper is `.claude/skills/verify/scripts/librag-verify`. Every command needs a run id:

```bash
export LIBRAG_VERIFY_RUN=$(date +%Y%m%d-%H%M%S)
V=.claude/skills/verify/scripts/librag-verify
```

## Launch

```bash
$V launch
```

- Runs `uv sync --frozen`, picks a free port on `127.0.0.1` (or `LIBRAG_VERIFY_PORT`), and starts `.venv/bin/python -m uvicorn librag.main:app` in the background, without reload.
- Ready means `GET /health` returned 200. The command prints `ready: http://127.0.0.1:<port> pid=<pid> run=<id>` and exits 0. It exits non-zero with the server log if the server dies or is not ready in 10 seconds.
- State goes to `.verify/<run id>/run/` (`pid`, `port`, `server.log`). `.verify/` is in `.gitignore`.
- Isolation: each run id has its own port and state, so two runs can go side by side. One run id holds one instance; `launch` refuses a second.
- Do not use `uv run fastapi dev`. Its reloader starts a child process, so the pid you hold is not the server.

## Doctor

```bash
$V doctor
```

Read-only. It passes only when all of these hold, and prints `ok: <url> pid=<pid> version=<v> run=<id>`:

- the pid from launch is alive;
- that pid owns the listening port (checked with `lsof`);
- `/health` returns exactly `{"status":"ok"}`;
- `/version` matches `version` in `pyproject.toml`. A mismatch means a stale install: run `$V cleanup`, then `$V launch`.

Run doctor before the first drive and again after any drive that surprised you.

## Drive

```bash
$V get <feature id> <path>
```

- Sends `GET <path>` to the instance and prints the request, the status, and the body.
- Saves `<name>.status`, `<name>.headers`, `<name>.body`, and a `<name>.txt` transcript under `.verify/<run id>/evidence/<feature id>/`. The name is the path with `/` and dots replaced, or `root` for `/`.
- The app has only GET routes. For other methods, use `curl` against the URL that `launch` printed, and save the output under the same evidence folder.

```bash
$V screenshot <feature id> <path> [platform]
```

- Opens `<path>` in headless Chrome or Chromium and saves `<name>.png` in the same evidence folder.
- Use it for routes that return HTML. A JSON route needs no screenshot; its response output is the proof.
- The helper looks for `LIBRAG_VERIFY_BROWSER`, then `/opt/pw-browsers/chromium` (the cloud container), then Google Chrome or Chromium on macOS, then `chromium` or `google-chrome` on `PATH`. - `platform` is one of the platforms in `design/README.md`: `desktop` (1280×800), `mobile` (390×844), `ios` (393×852), or `android` (412×915). It sets the window size and adds `_<platform>` to the file name. Without it, `LIBRAG_VERIFY_WINDOW` sets the size; the default is `1280,800`.
```bash
$V gallery <feature id> <page> [platform]
```

- Opens a gallery page from `design/`, such as `design/pages/search/empty.html`, from a file. It needs no server.
- Saves `gallery_<page>.png` in the feature's evidence folder, next to the app screenshots.
- For a ticket with the `ui` label, take the app screenshot and the gallery screenshot of the same screen state, so the two can be compared. Take both once for each platform in `design/README.md`.
- This helper drives LibRag as a web app. A native app needs its own app driver skill for app screenshots; the gallery screenshots still come from here.

- Screen recordings are for multi-step UI flows, such as filling in and sending a form. LibRag has no such flow yet. When one arrives, add a `record` command with Playwright video, and add a feature file for the flow.

The feature map in [features/README.md](features/README.md) has one recipe per feature, with the exact paths and the expected results.

## Evidence

A proof for a feature has, for every entry point that the feature file lists:

- the transcript (`.txt`) and status, headers, and body of each request;
- a screenshot (`.png`) for each HTML page, and for a ticket with the `ui` label, the gallery screenshot of the same state;
- the expected value next to the actual one, when you report it.

Proof standards:

- Drive the real server over HTTP. `TestClient` is the test suite's job, not proof here.
- Check the status, the content type, and the exact body. A 200 alone is not proof.
- Check the version against `pyproject.toml`, not against a value copied from an earlier run.
- No mocks. The app has no external systems.

In the factory, `factory-build` pastes the transcripts into the PR body and attaches the screenshots to the Linear ticket. `.verify/` is not committed, and a cloud container is deleted after the session.

## Cleanup

```bash
$V cleanup
```

- Stops only the pid that this run started (TERM, then KILL after 5 seconds). It never kills by process name.
- Copies `server.log` to the evidence folder, then removes `.verify/<run id>/run/`.
- Keeps `.verify/<run id>/evidence/`. Delete old runs by hand with `rm -rf .verify/<run id>` when you no longer need them.
- Run cleanup after every run, also after a failed one.

## Helpers

- `scripts/librag-verify launch|doctor|get <feature> <path>|screenshot <feature> <path>|gallery <feature> <page>|cleanup`: the only helper. It needs `bash`, `curl`, `lsof`, and `uv`, which are on macOS and on the cloud container. `screenshot` and `gallery` also need Chrome or Chromium.
