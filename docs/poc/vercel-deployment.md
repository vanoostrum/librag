# RAG POC: Vercel deployment (later phase)

Optional hosted deployment architecture. Reference design.

Transcribed from `rag_poc_vercel_deployment.pdf`, a steering note on the plan ticket LIBRAG-8. The POC plan does not build this. The plan keeps the design compatible with it, so a later phase can add it.

## Purpose

- Deploy the FastAPI web interface and chat orchestration on Vercel Hobby while using external managed services for persistent data and AI inference. This is an optional deployment target, not a prerequisite for local development or factory testing.

## Architecture

- **Vercel Hobby**: FastAPI endpoints, Jinja2/HTMX frontend, chat orchestration, provider routing via LiteLLM, citation formatting and lightweight query processing.
- **Qdrant Cloud**: Persistent dense and sparse/BM25 indexes, metadata filters and hybrid retrieval/fusion.
- **External AI APIs**: Generation through OpenAI/Anthropic/other configured providers; API embeddings and hosted reranking instead of loading local model weights into Vercel functions.
- **Persistent storage**: Store uploaded EPUB originals in object storage and book/job metadata in a hosted database. Neither local filesystem nor SQLite inside a Vercel function is persistent.
- **Ingestion worker**: Use a separate durable job runner/service to parse EPUBs, chunk, embed and index. API upload creates a job and returns promptly.

## Request flows

- Book upload: browser → FastAPI → object storage + job record → ingestion worker → Qdrant → job status update.
- Chat: browser → FastAPI → Qdrant hybrid retrieval → hosted reranker → selected passages → external LLM → answer with citations.
- Keep provider credentials on the server. Never expose them to the browser.

## Constraints and trade-offs

- Vercel functions are ephemeral and subject to memory, bundle-size and execution-time limits; avoid CPU-heavy local inference and long-running ingestion.
- Hobby suitability depends on current usage limits and non-commercial eligibility; verify Vercel terms and pricing before deployment.
- Network calls across services add latency and may add costs; monitor API usage and apply request timeouts and retries.
- Cloud architecture transmits selected book passages to external AI providers. Review privacy, copyright and retention requirements.

## Deployment checklist

- Configure Vercel Python/FastAPI build and environment variables; verify routes and static/template assets.
- Provision Qdrant Cloud collection(s), persistent book storage, hosted metadata store and ingestion runner.
- Set up secrets for Qdrant, storage, embeddings, reranker and LLM providers.
- Run a smoke test: upload EPUB, wait for indexing, retrieve passage, answer with citation.
- Use Docker Compose in CI for primary automated verification; optionally run a separate deployed smoke test against Vercel.

## Acceptance criteria

- Chat and library pages are accessible over HTTPS on Vercel.
- Uploaded books persist across deployments; ingestion continues independently of the HTTP request.
- A newly indexed book is searchable and its cited passages can be inspected.
- Switching supported external LLMs requires configuration rather than retrieval changes.
- Deployment does not depend on writable persistent local filesystem or local ML models.
