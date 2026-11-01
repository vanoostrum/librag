# LibRag verification map

This directory is the maintained source for verifying what an HTTP client sees from LibRag. Read this index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- `LIBRAG_VERIFY_RUN` is set and `V=.claude/skills/verify/scripts/librag-verify`.
- `$V launch` printed `ready:` and `$V doctor` printed `ok:` for this run.
- Never drive an instance that this run did not start.

## Driving conventions

- Drive every request with `$V get <feature id> <path>`, so the evidence lands in the feature's folder.
- Take a screenshot with `$V screenshot <feature id> <path>` for every HTML page.
- For a screen with a gallery page in `design/pages/`, also run `$V gallery <feature id> <page>` for each state that you drive.
- Use the paths exactly as written. `/health/` and `/health` are different routes.
- The app keeps state: uploaded books, their EPUB files and their passages stay in the run's database and file store under `.verify/<run id>/run/`. Each run has its own, and `cleanup` deletes them.
- To reset the library, start a new run: `$V cleanup`, set a new `LIBRAG_VERIFY_RUN`, then `$V launch`. A recipe that needs an empty library says so in its preconditions.

## Proof and skip reporting

- Report the status, the `content-type` header, and the exact body for each request.
- Record the feature ID with every artifact. The helper does this through the folder name.
- Report a path you could not reach with the command and the unmet precondition.
- Do not report a skipped path as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph on the behavior a client sees. Then come exactly four H2 sections, in this order: `Sub-features`, `How to get to it (user POV)`, `Driving it with librag-verify`, and `Gotchas`. Keep implementation details out of the map.

## Features

- [Library](./library.md) covers the Library page at `/`, its refresh at `GET /library/books`, and adding books in the browser.
- [Health](./health.md) covers the `/health` readiness check of Qdrant, the database and the worker.
- [Version](./version.md) covers `/version` and its match with `pyproject.toml`.
- [API docs disabled](./api-docs-disabled.md) covers the 404s for `/docs`, `/redoc`, and `/openapi.json`.
- [Books](./books.md) covers uploading an EPUB with `POST /api/books`, its parsing in the background, and the list at `GET /api/books`.
- [Search](./search.md) covers searching the indexed passages with `POST /api/rag/search`, with each retrieval stage.
- [Chat](./chat.md) covers answering questions with citations at `POST /api/chat`, streamed at `POST /api/chat/stream`, and the model list at `GET /api/config/models`.
- [Chat page](./chat-page.md) covers the Chat page at `/chat`: asking, the streamed answer, turns, the book picker, "Try again" and the remembered model, in the browser.
