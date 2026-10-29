# Required CI uses a real Qdrant and fake AI providers

The required `checks` job runs a real Qdrant as a service container, so tests exercise real dense, sparse and fused queries. Embeddings, reranking and generation are deterministic in-process fakes, so required CI needs no API keys and costs nothing. A separate, non-required CI job starts the full Docker Compose stack and runs `tests/e2e/` against it (`docs/poc/local-docker-compose.md`). Tests against real AI APIs are opt-in and never part of required CI.
