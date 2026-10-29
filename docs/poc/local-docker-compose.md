# RAG POC: Docker Compose and agent verification

Development and automated test architecture. Software factory reference.

Transcribed from `rag_poc_local_docker_compose_agent_verification.pdf`, a steering note on the plan ticket LIBRAG-8.

## Purpose

- Provide a reproducible environment that a cloud software-factory agent can start, exercise and tear down to verify real application behavior. Docker Compose is feasible when the agent has a Docker daemon or access to a Docker-enabled CI runner.

## Compose services

- **api**: FastAPI backend, Jinja2/HTMX pages and health endpoints.
- **qdrant**: Persistent vector/sparse search database, using disposable test volumes in CI.
- **worker**: Separate ingestion process that reads uploaded EPUBs and indexes chunks.
- **metadata**: SQLite mounted in a volume for local POC; use a test database/volume for CI. PostgreSQL is optional if concurrency requires it.
- **mock-ai**: Deterministic HTTP fixtures or a mock API for embeddings, reranking and generation. Real API calls belong in opt-in live tests.
- **test-runner**: Container with pytest and fixtures, sharing the Compose network.

## Verification modes

- **Deterministic CI (default)**: Run parsing, indexing, retrieval, citation and API tests with fixed test data and mocked external AI calls. No secrets or paid API calls required.
- **Live integration (opt-in)**: Use real embedding/reranking/LLM APIs with limited test budgets, credentials and tolerant quality checks. Run separately from required CI.
- **Deployment smoke tests**: Optionally check a deployed Vercel endpoint; do not make deployed cloud availability a prerequisite for local functional tests.

## Agent execution workflow

- Check Docker availability (`docker info`) and Compose plugin before starting. If unavailable, delegate to a Docker-enabled runner.
- Build and start isolated services using `docker compose -f compose.yaml -f compose.test.yaml up -d --build --wait`.
- Wait for explicit readiness checks for FastAPI, Qdrant and worker dependencies.
- Load fixture EPUBs through public API endpoints; poll ingestion status until indexed.
- Run `pytest tests/e2e/` against the running stack, checking hybrid retrieval, citations and cross-book answers.
- Collect structured logs, test reports, relevant response payloads and failed container status.
- Always tear down the test stack and disposable volumes with `docker compose ... down -v`, even on failure.

## Test design

- Use small, redistributable EPUB fixtures with known passages, chapters and expected citations.
- For deterministic embedding tests, use stable vector fixtures or a mock embedding service; test Qdrant dense + sparse retrieval and fusion with real database calls.
- Test idempotent uploads, incremental indexing, book metadata, failure recovery, search diagnostics and two provider configurations.
- Separate fast unit tests from end-to-end tests and live quality benchmarks. Avoid brittle exact-string comparisons of generative answers.

## Operational guardrails

- Pin image and Python dependency versions; use isolated Compose project names for concurrent agents.
- Never commit API keys; inject live-test secrets from CI secret storage.
- Set CPU/memory budgets and timeouts; avoid heavyweight local ML models in cloud-agent runners.
- Preserve logs on failure and ensure worker errors propagate to observable job status.
- Document minimum Docker, disk, RAM and network prerequisites.

## Acceptance criteria

- A Docker-capable agent can start the stack from a clean checkout with one documented command.
- Health checks pass and a fixture EPUB can be uploaded, indexed and searched.
- E2E tests verify actual FastAPI ↔ worker ↔ Qdrant interaction and grounded citation IDs.
- Deterministic test suite runs without external paid AI API credentials.
- Live integration tests can be enabled separately and report token usage/cost.
- All services are torn down and test artifacts retained for debugging.
