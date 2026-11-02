# Contextual enrichment

Contextual enrichment lets an LLM write a short *context line* for each passage while the worker indexes a book. The line says who and what the passage is about, in the book's own terms. Dense search and BM25 both index it with the passage. The passage's own text stays unchanged: citations, the Chat page and the diagnostics never show the line. Only `POST /api/rag/search` returns it, as `context` on each result and candidate.

Enrichment is off by default. Turn it on only to measure it, and keep it only if the [retrieval evaluation](evaluation.md) shows that it helps.

## Turn it on

Set two variables for the worker and the api, then restart the stack:

| Variable | Default | What |
|---|---|---|
| `LIBRAG_ENRICHMENT` | `off` | `on` makes the worker write a context line for each passage. |
| `LIBRAG_ENRICHMENT_MODEL` | `anthropic/claude-haiku-5-5` | The LiteLLM model that writes the lines. It needs its provider's key, such as `ANTHROPIC_API_KEY`. |

```bash
export ANTHROPIC_API_KEY=sk-ant-...
LIBRAG_ENRICHMENT=on docker compose up -d --build --wait
```

Each book that you upload now gets context lines. A book indexed before the change is out of date: with `LIBRAG_REINDEX_ENABLED=on`, the Library page says "Out of date: indexed without enrichment". Reindex writes its lines and embeds the passages again. It does not parse the EPUB again, so the passage IDs stay the same. Turning enrichment off marks the enriched books out of date in the same way ("indexed with enrichment"), and their reindex removes the lines.

A change of only the embedding model keeps the stored lines. Its reindex embeds again and makes no LLM calls.

## How a line is written

Each call sends the passage's chapter, then the passage. The chapter is a cached block, so the provider reads it from its prompt cache for every later passage of that chapter. The prompt asks for one sentence of at most 50 tokens, without commentary. The worker puts the reply on one line and cuts it to 80 tokens.

A failed call is tried again after 1, 2 and 4 seconds, as an embedding batch is. If it still fails, the book fails with "Enrichment failed: <error>", and Retry runs its ingestion again.

The worker writes the lines one passage at a time, so enrichment makes indexing slower. A novel of about 400 passages takes some minutes.

## What it costs

`GET /api/books` reports, for each book, `index_configuration.enrichment_model` (or `null`), `enrichment_input_tokens`, `enrichment_output_tokens` and `enrichment_cost_usd`. LiteLLM computes the cost, with the cache prices.

A rough estimate for Claude Haiku 5.5: a novel of 120,000 tokens has about 400 passages. Each call reads its chapter from the cache, and adds the passage and a line of about 50 tokens. That is about 5 to 20 cents per novel, and less than $1 for the 4 evaluation books. A chapter shorter than the provider's minimum cache size goes uncached, which costs a little more. Check the estimate against `enrichment_cost_usd` after the first real run.

## Measure it

Compare two runs of the [retrieval evaluation](evaluation.md), one without and one with enrichment, on the same stack:

1. Run `scripts/eval-retrieval` with enrichment off. This is the baseline.
2. Restart the stack with `LIBRAG_ENRICHMENT=on`.
3. Run `scripts/eval-retrieval` again. It uploads the 4 books again, so the worker enriches them.
4. Compare the two reports in `eval-reports/`. Each report records `index_configuration.enrichment_model` per book, so you can see which run is which.

If you keep the evaluation books with `--keep-books`, reindex them after step 2 instead: `POST /api/books/reindex-out-of-date` with `LIBRAG_REINDEX_ENABLED=on`. Compare the runs only when the rest of the library is the same, because BM25 weighs words over the whole collection.
