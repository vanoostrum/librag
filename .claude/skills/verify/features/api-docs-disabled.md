# API docs disabled

The interactive API docs and the OpenAPI schema are off. A client that asks for them gets a 404.

## Sub-features

- `docs-swagger-off` returns 404 for `/docs`.
- `docs-redoc-off` returns 404 for `/redoc`.
- `docs-openapi-off` returns 404 for `/openapi.json`.

## How to get to it (user POV)

- Open `/docs` or `/redoc` in a browser.
- Send `GET /openapi.json`, as a client generator does.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.

- **Swagger UI.** Run `$V get api-docs-disabled /docs`. Status is `404` and the body is `{"detail":"Not Found"}`.
- **ReDoc.** Run `$V get api-docs-disabled /redoc`. Status is `404` and the body is `{"detail":"Not Found"}`.
- **Schema.** Run `$V get api-docs-disabled /openapi.json`. Status is `404` and the body is `{"detail":"Not Found"}`.

## Gotchas

- A 404 here is the pass. A 200 means someone turned the docs back on.
