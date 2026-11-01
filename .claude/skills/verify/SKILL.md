---
name: verify
description: Drive the running LibRag FastAPI app over HTTP and capture evidence that a route behaves as specified. Use to prove a change in the real app (homepage, /health, /version, the books API, search, disabled API docs), not just in tests. For lint, type check, and tests, use project-verify.
---

# Verify LibRag in the running app

LibRag is an HTTP service. The user surface is its routes: `/` (HTML homepage), `/health`, `/version`, the books API (`POST /api/books`, `GET /api/books`), and search (`POST /api/rag/search`). The API docs (`/docs`, `/redoc`, `/openapi.json`) are off on purpose. The app runs as a stack: `api`, `worker`, Qdrant and a SQLite metadata database. There is no UI framework, auth, or seed data. The driver is `curl`, wrapped by one helper script.

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

- Runs `uv sync --frozen`, then starts the stack in one of two modes. It prints the mode it chose.
- **Compose mode** (the default when Docker works): `docker compose -f compose.yaml -f compose.test.yaml up -d --build --wait`, as Compose project `librag-verify-<run id>`. The api gets a free port on `127.0.0.1` (or `LIBRAG_VERIFY_PORT`), and Qdrant gets another one.
- **Process mode** (the fallback): when Docker is missing, its daemon is not running, or it cannot pull an image, `launch` prints `compose mode unavailable: <reason>` and starts each part as a local process:
  1. Qdrant from the pinned release binary. The first run downloads it to `.verify/bin/` and checks its SHA-256. Its version is the same as the `qdrant` image in `compose.yaml`.
  2. `alembic upgrade head`, the same step as the `migrate` service.
  3. The api (`uvicorn`, without reload) and the worker (`python -m librag.worker`).
  `.claude/settings.json` allows Claude Code to run that pinned binary (`Bash(.verify/bin/qdrant-v1.15.5-*/qdrant:*)`). Update the rule when you change the version.
  Every process reads `compose.test.env`, the env file of `compose.test.yaml`, so both modes use the same test settings. The database and the Qdrant data live under `.verify/<run id>/run/`.
- Set `LIBRAG_VERIFY_MODE=compose` or `LIBRAG_VERIFY_MODE=process` to force a mode.
- Ready means `GET /health` returned 200. The command prints `ready: http://127.0.0.1:<port> mode=<compose|process> run=<id>` and exits 0. It exits non-zero with the logs if a part dies or `/health` is not 200 in 60 seconds.
- State goes to `.verify/<run id>/run/` (`mode`, `port`, and in process mode a `.pid` and `.log` per process). `.verify/` is in `.gitignore`.
- Isolation: each run id has its own ports, state and Compose project, so two runs can go side by side. One run id holds one instance; `launch` refuses a second.
- The cloud sandbox has no running Docker daemon and cannot pull images, so it uses process mode. CI's `e2e` job is the proof of the Compose files.
- Do not use `uv run fastapi dev`. Its reloader starts a child process, so the pid you hold is not the server.

## Doctor

```bash
$V doctor
```

Read-only. It passes only when all of these hold, and prints `ok: <url> mode=<mode> version=<v> run=<id>`:

- compose mode: the `qdrant`, `api` and `worker` services of this run's project are running;
- process mode: the Qdrant, api and worker pids from launch are alive, and the api pid owns the listening port (checked with `lsof`);
- `/health` returns exactly `{"status":"ok","checks":{"qdrant":"ok","database":"ok","worker":"ok"}}`;
- `/version` matches `version` in `pyproject.toml`. A mismatch means a stale install: run `$V cleanup`, then `$V launch`.

Run doctor before the first drive and again after any drive that surprised you.

## Drive

```bash
$V get <feature id> <path>
```

- Sends `GET <path>` to the instance and prints the request, the status, and the body.
- Saves `<name>.status`, `<name>.headers`, `<name>.body`, and a `<name>.txt` transcript under `.verify/<run id>/evidence/<feature id>/`. The name is the path with `/` and dots replaced, or `root` for `/`.
- `$V get` sends only GET. For other methods, such as `POST /api/books`, use `curl` against the URL that `launch` printed, and save the output under the same evidence folder. The feature file gives the command.

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
- No mocks. The stack uses a real Qdrant and a real database. `compose.test.env` selects the in-process fake AI providers, so verify needs no API keys.

In the factory, `factory-build` pastes the transcripts into the PR body and attaches the screenshots to the Linear ticket. `.verify/` is not committed, and a cloud container is deleted after the session.

## Cleanup

```bash
$V cleanup
```

- Compose mode: saves `docker compose logs` as `compose.log` in the evidence folder, then runs `docker compose down -v` for this run's project only.
- Process mode: stops only the pids that this run started (TERM, then KILL after 5 seconds). It never kills by process name. It copies `qdrant.log`, `migrate.log`, `api.log` and `worker.log` to the evidence folder.
- Then it removes `.verify/<run id>/run/`, with the run's database and Qdrant data.
- Keeps `.verify/<run id>/evidence/`. Delete old runs by hand with `rm -rf .verify/<run id>` when you no longer need them.
- Run cleanup after every run, also after a failed one.

## Helpers

- `scripts/librag-verify launch|doctor|get <feature> <path>|screenshot <feature> <path>|gallery <feature> <page>|cleanup`: the only helper. It needs `bash`, `curl`, `lsof`, `tar`, and `uv`, which are on macOS and on the cloud container. Compose mode also needs Docker with the Compose plugin. `screenshot` and `gallery` also need Chrome or Chromium.
