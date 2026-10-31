# Health

A client or a monitor that calls `/health` gets a JSON status that says whether Qdrant, the metadata database and the worker are ready. It is 200 when all three are, and 503 when any one is not.

## Sub-features

- `health-ok` returns 200 with exactly `{"status":"ok","checks":{"qdrant":"ok","database":"ok","worker":"ok"}}`.
- `health-worker-down` returns 503 with `status` and `checks.worker` set to `"unavailable"` when the worker has not written a heartbeat for 30 seconds.
- `health-qdrant-down` returns 503 with `status` and `checks.qdrant` set to `"unavailable"` when Qdrant does not answer.

## How to get to it (user POV)

- Send `GET /health`, as a load balancer or uptime monitor does.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.

- **Call health.** Run `$V get health /health`. Status is `200` and the body is exactly `{"status":"ok","checks":{"qdrant":"ok","database":"ok","worker":"ok"}}`.
- **Check the type.** Read `.verify/$LIBRAG_VERIFY_RUN/evidence/health/health.headers`. It has `content-type: application/json`.
- **Worker down (process mode).** Stop the worker with `kill $(cat .verify/$LIBRAG_VERIFY_RUN/run/worker.pid)`. Wait 31 seconds. Run `curl -sS -w '\n%{http_code}\n' <url>/health > .verify/$LIBRAG_VERIFY_RUN/evidence/health/worker-down.txt`. Status is `503` and the body is `{"status":"unavailable","checks":{"qdrant":"ok","database":"ok","worker":"unavailable"}}`. This run cannot go back to ready: run `$V cleanup`.
- **Worker down (compose mode).** Run `docker compose -p librag-verify-<run id> stop worker`, then do the same as in process mode.
- **Qdrant down.** Stop Qdrant the same way (`qdrant.pid`, or the `qdrant` service). `/health` is `503` with `checks.qdrant` `"unavailable"` at once.

## Gotchas

- `launch` and `doctor` also call `/health`. Those calls are not the proof. Drive it with `$V get` so the evidence is in this feature's folder.
- `/health/` with a trailing slash is a different path. FastAPI answers it with a redirect, not with the status.
- The route tests cover each 503 case. Drive the down cases only when a ticket changes them, and drive them last, because they break the run.
