# POC Brief — Personal Book RAG Assistant

## 1. Objective

Build a proof-of-concept AI assistant that uses a personal library of books as a specialized knowledge source.

The assistant must automatically retrieve relevant information from the books when answering questions, including questions that do not explicitly mention the library.

The system should support factual lookup, conceptual questions, cross-book comparisons and synthesis of ideas across multiple authors.

**Key principles:**
- High-quality retrieval using sophisticated RAG techniques.
- Modular architecture with clearly separated responsibilities.
- Incremental book ingestion.
- Model-independent integration with external LLM APIs.
- Traceable answers with book citations.
- Minimal web interface using FastAPI.
- Focus on retrieval quality, experimentation and maintainability rather than production infrastructure.

## 2. High-level architecture

The application consists of two main subsystems.

### A. Book ingestion and indexing

Responsible for converting books into a persistent, searchable knowledge base.

```text
EPUB upload
    ↓
Parse book structure and metadata
    ↓
Extract chapters, sections and paragraphs
    ↓
Create structure-aware chunks
    ↓
Generate contextual chunk representations
    ↓
Generate dense embeddings + sparse/BM25 index
    ↓
Store chunks, vectors and metadata in Qdrant
```

Requirements:

- Initially support EPUB files containing extractable text.
- Preserve title, author, chapter, section and source location.
- Prefer semantic boundaries over fixed-size chunking.
- Support configurable chunk sizes and overlap.
- Make contextual chunk enrichment optional and configurable.
- Allow books to be added, replaced, re-indexed and deleted independently.
- Use deterministic book and chunk identifiers.
- Track ingestion status, errors, book versions and indexing configuration.
- Ensure that re-indexing a book does not produce duplicate chunks.
- Store original source files separately from the vector database.

### B. Chat and RAG query runtime

Responsible for finding relevant passages and generating grounded answers.

```text
User question
    ↓
Query analysis
    ↓
Optional query rewriting / decomposition
    ↓
Hybrid retrieval
    ├── Dense semantic search
    └── Sparse/BM25 search
    ↓
Reciprocal Rank Fusion (RRF)
    ↓
Cross-encoder reranking
    ↓
Context selection (top 8–12 passages)
    ↓
LLM API (configurable provider/model)
    ↓
Grounded answer + source citations
```

Requirements:

- Automatically consider the book library for every substantive question.
- Support questions about individual books and across multiple books.
- Allow filtering by book, author or other metadata.
- Use general LLM knowledge when appropriate, distinguishing it from book-derived information.
- Never attribute claims to a book without supporting retrieved evidence.
- Return structured citation references linked to the original passages.
- Support streaming LLM responses.
- Allow switching LLM providers/models through configuration.

## 3. Technology stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend/API | FastAPI |
| Minimal frontend | Jinja2 + HTMX + minimal JavaScript |
| EPUB parsing | ebooklib + BeautifulSoup + lxml |
| Tokenization | tiktoken or model-specific tokenizer |
| Chunking | Custom Python implementation |
| Data validation | Pydantic |
| Vector database | Qdrant (Docker) |
| Dense embeddings | sentence-transformers or embedding API |
| Sparse retrieval | Qdrant BM25/sparse vectors |
| Fusion | Qdrant RRF |
| Reranking | sentence-transformers CrossEncoder |
| LLM integration | LiteLLM |
| Book registry / job metadata | SQLite initially |
| Background processing | Separate worker process; optionally ARQ + Redis |
| Retrieval evaluation | ranx |
| Answer evaluation | Ragas + manually reviewed test cases |
| Observability | Structured logging; optional Langfuse |
| Testing | pytest |
| Dependency management | uv |
| Infrastructure | Docker Compose |

**LLM providers:** Initially OpenAI and Anthropic, with support for Gemini and Grok through LiteLLM.

No local generative LLM is required. Local embedding and reranking models are permitted because they are lightweight and independent of the generative LLM.

## 4. FastAPI project structure

Use a modular Python project with the following suggested structure:

```text
project/
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   ├── books.py
│   │   ├── chat.py
│   │   └── search.py
│   │
│   ├── rag/
│   │   ├── ingestion/
│   │   │   ├── epub_parser.py
│   │   │   ├── chunker.py
│   │   │   ├── indexer.py
│   │   │   └── pipeline.py
│   │   │
│   │   ├── retrieval/
│   │   │   ├── dense.py
│   │   │   ├── hybrid.py
│   │   │   ├── reranker.py
│   │   │   └── pipeline.py
│   │   │
│   │   ├── embeddings/
│   │   │   └── provider.py
│   │   │
│   │   └── evaluation/
│   │
│   ├── llm/
│   │   ├── provider.py
│   │   ├── prompts.py
│   │   └── chat_service.py
│   │
│   ├── models/
│   ├── services/
│   │   └── book_service.py
│   │
│   ├── templates/
│   └── static/
│
├── workers/
│   └── ingestion_worker.py
│
├── tests/
│   ├── ingestion/
│   ├── retrieval/
│   └── evaluation/
│
├── data/
│   └── books/
│
├── pyproject.toml
├── docker-compose.yml
├── .env.example
└── README.md
```

The HTTP/API layer must remain thin. Core RAG logic should be implemented as independently testable Python services, without dependencies on FastAPI request objects.

## 5. Architectural decisions

### AD-01 — Separate ingestion from query execution

Ingestion and chat are independent workflows sharing the same knowledge base.

Book ingestion should run in a background worker, not block FastAPI request handling.

New books become searchable after successful indexing without restarting the application.

### AD-02 — Incremental and reproducible indexing

Every book must have a stable identity and content hash.

Indexing must be idempotent. Re-indexing unchanged content with unchanged configuration should not create duplicates.

Store indexing configuration and embedding model versions. Changing embedding models may require regenerating vectors, but should not require reparsing the source EPUB.

### AD-03 — Hybrid retrieval as the default

Use both dense semantic retrieval and BM25 lexical retrieval.

Initial configurable defaults:

- Dense retrieval: top 30.
- BM25 retrieval: top 30.
- Fusion: RRF.
- Reranking: combined candidate pool.
- Final context: approximately 8–12 passages, subject to token budget.

These are starting values, not fixed assumptions. They must be tunable and measurable.

### AD-04 — Structure-aware chunking

Preserve the logical structure of books.

Chunks should normally stay within chapter/section boundaries. Avoid splitting paragraphs unnecessarily.

Retain chapter headings and contextual metadata to help retrieval.

Optional contextual enrichment should be supported without modifying the original extracted text.

### AD-05 — Provider-independent LLM integration

Use LiteLLM behind an application-level provider interface.

The generation model must be configurable independently of the retrieval pipeline.

The same question and retrieved context should be executable against different LLMs for quality and cost comparisons.

Store model identifiers, token usage, latency and estimated API costs for each request.

### AD-06 — Inspectable retrieval pipeline

Each retrieval stage must be independently executable and inspectable.

Expose a search endpoint that returns results without invoking the generative LLM.

Capture:

- Original and rewritten queries.
- Dense and BM25 candidates.
- Fusion results and scores.
- Reranking results and scores.
- Final selected context.
- LLM response and citation references.

### AD-07 — Grounded answers and citation integrity

Every book-derived citation must reference an actual retrieved passage.

Maintain a mapping between citation identifiers and source metadata.

The LLM must distinguish between:

1. Claims supported by the books.
2. Synthesis or interpretation of book content.
3. General knowledge not sourced from the library.

The system should acknowledge missing evidence rather than inventing book references.

### AD-08 — Minimal dependencies and infrastructure

Avoid introducing LangChain, LlamaIndex or other large orchestration frameworks unless they provide a demonstrated advantage.

Implement the core pipeline explicitly.

Use SQLite for application metadata and Qdrant for retrieval. Avoid introducing Redis, PostgreSQL or distributed infrastructure unless required.

### AD-09 — Evaluation-driven development

Build a repeatable evaluation suite covering both retrieval and generation.

Keep retrieval evaluation separate from answer-quality evaluation so failures can be attributed to the correct stage.

All retrieval parameters and model configurations should be adjustable without changing application logic.

## 6. API and minimal web interface

### API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/books` | Upload and enqueue a book |
| `GET /api/books` | List books and ingestion status |
| `DELETE /api/books/{id}` | Delete a book and its index |
| `POST /api/books/{id}/reindex` | Re-index a book |
| `POST /api/rag/search` | Retrieve ranked passages without LLM |
| `POST /api/chat` | Ask a question |
| `POST /api/chat/stream` | Stream an answer |
| `GET /api/config/models` | List configured LLM models |

### Web interface

Implement two minimal pages:

**Library management**
- Upload EPUB.
- View indexed books and ingestion status.
- Delete or re-index books.

**Chat**
- Ask questions in natural language.
- Select LLM model.
- View streaming answers with citations.
- Inspect supporting retrieved passages.
- Optionally display retrieval diagnostics.

Use server-rendered Jinja2 templates with HTMX and minimal JavaScript. A separate frontend framework is unnecessary for the POC.

## 7. Acceptance criteria

### Ingestion and library management

- [ ] AC-01: Uploading a valid EPUB creates a background ingestion job and makes the book searchable after completion.
- [ ] AC-02: Adding a book does not require reprocessing existing books.
- [ ] AC-03: Re-indexing or deleting a book updates the search index without affecting other books.
- [ ] AC-04: Repeated ingestion of the same book/configuration does not create duplicate entries.
- [ ] AC-05: Chunks retain accurate book, author, chapter/section and source-location metadata.

### Retrieval

- [ ] AC-06: Hybrid retrieval combines semantic and BM25 results using RRF.
- [ ] AC-07: A reranking stage reorders candidates before context selection.
- [ ] AC-08: Retrieval parameters are configurable.
- [ ] AC-09: Search results can be inspected independently of the LLM.
- [ ] AC-10: Queries can retrieve relevant passages from multiple books.

### Chat and LLM

- [ ] AC-11: Ordinary questions automatically use relevant library content without explicit search instructions.
- [ ] AC-12: The assistant can answer factual, conceptual and cross-book synthesis questions.
- [ ] AC-13: Book-derived answers include verifiable source citations.
- [ ] AC-14: Unsupported book attributions are avoided; missing evidence is acknowledged.
- [ ] AC-15: Switching between at least two external LLM providers requires configuration only.
- [ ] AC-16: Streaming responses work in the web interface.
- [ ] AC-17: Questions unrelated to the library can still receive useful general-knowledge answers.

### Observability and evaluation

- [ ] AC-18: Retrieval candidates, ranking scores and final context are inspectable.
- [ ] AC-19: LLM model, token usage, latency and estimated API cost are logged.
- [ ] AC-20: An evaluation dataset of at least 20 questions exists, including factual, conceptual, cross-book, indirect-relevance and negative cases.
- [ ] AC-21: The evaluation suite reports retrieval metrics (at minimum Recall@K and MRR) and supports manual assessment of answer quality and citation accuracy.
- [ ] AC-22: Tests cover parsing, chunking, indexing, deletion and retrieval.


## 8. Out of scope

The initial POC does not require:

- Local generative LLMs.
- Multi-user authentication or authorization.
- Production-grade deployment and scaling.
- A separate React/Vue frontend.
- Fine-tuning.
- Knowledge graphs or GraphRAG.
- PDF/OCR ingestion.
- Agentic workflows beyond optional query decomposition.

## 9. Definition of done

The POC is complete when a user can:

1. Upload several EPUB books through the web interface.
2. Ask natural-language questions without manually invoking retrieval.
3. Receive useful answers grounded in relevant passages from one or multiple books.
4. Inspect citations and supporting passages.
5. Switch between external LLM providers.
6. Add, re-index and delete books without rebuilding the entire library.
7. Inspect retrieval diagnostics and run repeatable quality evaluations.

**Primary success criterion:** Demonstrate a reliable, measurable, extensible RAG pipeline that makes the contents of a personal book library automatically available to an API-based AI assistant.

Prioritize retrieval quality, source traceability and clean architecture over UI polish or infrastructure complexity.
