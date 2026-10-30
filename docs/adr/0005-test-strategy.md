# Fake AI providers by configuration, with a real Qdrant

The embedder, the reranker and the LLM each have a deterministic fake inside the app, and configuration picks the fake or the real provider. Required CI (`checks`) runs a real Qdrant as a service container and the fakes, so tests exercise real dense, sparse and fused queries, need no API keys, and cost nothing. The Compose stack takes the same configuration: `compose.test.yaml` selects the fakes, so the factory's app driver and the `tests/e2e/` suite run the full stack without paid credentials (`docs/poc/local-docker-compose.md`). The e2e suite runs in a separate, non-required CI job. Tests against real AI APIs are opt-in and never part of required CI.

## Considered options

The Compose note suggests a separate `mock-ai` HTTP service. In-process fakes chosen by configuration give the same determinism with one service fewer, and they also cover the reranker, which runs in-process and which an HTTP mock cannot replace.
