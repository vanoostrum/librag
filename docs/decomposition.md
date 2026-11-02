# Question decomposition

Decomposition lets the LLM split a complex question into *sub-questions* before the search. A question such as "How do Kahneman and Taleb each advise decision makers, and where do they disagree?" asks about several things. One search for the whole question can miss passages that only answer one part. With decomposition, each sub-question is searched on its own, and the results are fused and then reranked against the whole question. Chat still makes one answer call.

Decomposition is off by default. Turn it on only to measure it, and keep it only if the evaluations show that it helps.

## How it works

1. Chat rewrites a follow-up into a standalone search query, as without decomposition.
2. The LLM gets the search query and decides whether to split it. It replies with 1 to 4 queries. The call uses the request's chat model and counts in the request's `usage` and in the usage log.
3. A query that the LLM does not split is searched as usual. A split query runs the dense, BM25 and fusion stages once per sub-question.
4. A reciprocal rank fusion over the sub-questions' fusion lists gives the fused candidates. The reranker scores the first `fusion_k` of them against the search query, not against a sub-question.
5. The context and the answer follow as without decomposition.

A reply that is not the JSON that the prompt asks for, an empty list, or a provider error keeps the one search query. A reply with more than 4 queries keeps the first 4. A decomposition never fails a request.

## Turn it on

Set the variable for the api, then restart the stack:

```bash
LIBRAG_DECOMPOSE=on docker compose up -d --wait
```

| Variable | Default | What |
|---|---|---|
| `LIBRAG_DECOMPOSE` | `off` | `on` makes chat ask the LLM to split the search query into sub-questions. |

Search does not read the variable. A `POST /api/rag/search` request asks for decomposition itself, with `"decompose": true`, and can name the chat model that splits with `"model"`. Without `model`, it uses the default chat model.

## What the responses show

Chat's `retrieval`, the stream's `done` event and search's response have `queries`: one entry per query that was searched, `Q1` to `Q4`, with its `text` and its own `dense`, `bm25` and `fusion` stages. Without decomposition, `queries` holds the search query alone, as `Q1`.

The top-level `stages` are over all queries. `fusion` and `rerank` are the fused and reranked lists. `dense` and `bm25` list each passage once, at its best rank over the sub-questions. Each candidate has `found_by`, the IDs of the queries whose fusion list holds it.

On the Chat page, "How this answer was found" shows "Search queries", "split into N" and the numbered sub-questions, and each card has a "Found by" chip. A question that was not split shows the one search query, as without decomposition.

## Measure it

Compare runs with and without decomposition, on the same stack and library.

**Retrieval.** Run the [retrieval evaluation](evaluation.md) twice:

```bash
scripts/eval-retrieval --keep-books
scripts/eval-retrieval --decompose
```

The second run asks search to split each question. It makes one short LLM call per question, with the default chat model, or the one that `--model` names. The report records `"decompose": true` and, under `sub_questions`, the queries that each question was split into, so you can read how the model split them. Compare the `fusion` and `rerank` rows of the two reports. The baseline before this feature was R@10 0.58 and MRR 0.40 for fusion, and R@10 0.45 and MRR 0.36 for rerank.

**Answers.** Run the [answer evaluation](answer-evaluation.md) once with `LIBRAG_DECOMPOSE` off and once with it on, restarting the stack in between. Compare the grades, the Ragas scores and the latency in the two summaries. A split question costs one more LLM call and 2 to 4 searches, so it answers more slowly.
