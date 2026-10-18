# Health

A client or a monitor that calls `/health` gets a JSON status that says the service is up.

## Sub-features

- `health-ok` returns 200 with exactly `{"status":"ok"}`.

## How to get to it (user POV)

- Send `GET /health`, as a load balancer or uptime monitor does.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.

- **Call health.** Run `$V get health /health`. Status is `200` and the body is exactly `{"status":"ok"}`.
- **Check the type.** Read `.verify/$LIBRAG_VERIFY_RUN/evidence/health/health.headers`. It has `content-type: application/json`.

## Gotchas

- `launch` and `doctor` also call `/health`. Those calls are not the proof. Drive it with `$V get` so the evidence is in this feature's folder.
- `/health/` with a trailing slash is a different path. FastAPI answers it with a redirect, not with the status.
