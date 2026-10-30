# Fake AI providers by configuration, with a real Qdrant, and a required e2e check

The embedder, the reranker and the LLM each have a deterministic fake inside the app, and configuration picks the fake or the real provider. Two CI jobs are required before a merge. `checks` runs ruff, ty and pytest against a real Qdrant service container with the fakes, so tests exercise real dense, sparse and fused queries. `e2e` starts the Docker Compose stack with `compose.test.yaml`, which selects the fakes, runs `tests/e2e/` against it, and tears it down (`docs/poc/local-docker-compose.md`). Neither job needs API keys or costs money. The factory's app driver uses the same overlay. Tests against real AI APIs are opt-in and never required.

## Considered options

- The Compose note suggests a separate `mock-ai` HTTP service. In-process fakes chosen by configuration give the same determinism with one service fewer, and they also cover the reranker, which runs in-process and which an HTTP mock cannot replace.
- The e2e suite could run as a non-required job to keep merges fast. Theo chose to require it: a broken stack must block a merge, even if each PR waits a few minutes longer.
