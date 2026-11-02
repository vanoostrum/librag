# Decompose

With `LIBRAG_DECOMPOSE=on`, chat asks the LLM whether the search query asks about several things, and splits it into 2 to 4 sub-questions. Each sub-question is searched; their fusion lists are fused again and reranked against the search query. Search does the same when its request has `"decompose": true`, with the request's `model` or the default chat model. Chat, its stream's `done` event and search list the `queries` that were searched, and each candidate's `found_by`. On the Chat page, the diagnostics of a split question show "Search queries", "split into N" with the numbered sub-questions, and a "Found by" chip on each card.

## Sub-features

- `decompose-off`: with the switch off, chat makes no decompose call; `retrieval.queries` holds one entry, `Q1`, with the search query, and each fused candidate has `found_by: ["Q1"]`.
- `decompose-split`: with the switch on, the fake LLM splits on " and ". `queries` lists `Q1` to `QN` with their texts and their own `dense`, `bm25` and `fusion` stages; the top-level `fusion` and `rerank` are the lists over all of them, and top-level `dense` and `bm25` give each passage its best rank over the sub-questions.
- `decompose-usage`: the decompose call's tokens count in `usage` and in the `chat_usage` row.
- `decompose-search`: `POST /api/rag/search` with `"decompose": true` returns `queries` and `found_by` like chat; without it, `queries` holds the query alone. An unknown `model` is `422`.
- `decompose-page`: the Chat page's diagnostics of a split question, against `design/pages/chat/diagnostics-decomposed.html`; a question that is not split still matches `design/pages/chat/diagnostics.html`.

## How to get to it (user POV)

- Start the stack with `LIBRAG_DECOMPOSE=on`, then ask a question in Chat that asks about two or more things. Open "How this answer was found".
- For the API, `POST /api/rag/search` with `"decompose": true`.

## Driving it with librag-verify

Preconditions:

- Two runs: one launched as usual (the switch off), and one launched with `LIBRAG_DECOMPOSE=on $V launch` under its own `LIBRAG_VERIFY_RUN`. Process mode passes the variable to the api; compose mode passes it through `compose.yaml`.
- In each run, index the Sea Stories and Harbour Tales books of the [Chat](./chat.md) recipe, with its `post` helper, and use its `ask` and `usage` helpers with `E=.verify/$LIBRAG_VERIFY_RUN/evidence/decompose`.

```bash
search() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -H 'content-type: application/json' -d "$1" $URL/api/rag/search | tee $E/$2.txt; }
```

- **Off.** In the off run, run `ask '{"question":"lighthouse keeper and wild strawberries"}' off`. `retrieval.queries` is one entry, `Q1`, with the whole question; `usage` matches one call.
- **Split.** In the on run, run `ask '{"question":"lighthouse keeper and wild strawberries and harbour fog"}' split`. `retrieval.queries` is `Q1` "lighthouse keeper", `Q2` "wild strawberries", `Q3` "harbour fog"; each candidate's `found_by` lists the queries whose `stages.fusion` holds it; the strawberries passage is found by `Q2`. Then `usage` shows the row with the response's tokens.
- **Not split.** In the on run, run `ask '{"question":"lighthouse keeper"}' single`: `queries` is `Q1` alone.
- **Search.** In the off run, run `search '{"query":"lighthouse keeper and wild strawberries","decompose":true}' search-split` (two queries) and `search '{"query":"lighthouse keeper and wild strawberries"}' search-single` (one query). Then `search '{"query":"x","decompose":true,"model":"acme/nope"}' search-bad-model`: `422`, `{"error":"model: 'acme/nope' is not one of the chat models"}`.
- **Page.** In the on run, for each platform, run `node .claude/skills/verify/scripts/chat-browser.js $URL $E decomposed <platform>`. The transcript `browser_decomposed_<platform>.txt` shows the summary rows Question, Search queries ("split into 3" and the three sub-questions), Model and Retrieval (starting "3 searches, fused, then reranked against the question"); each card's first chip is "Found by Q…"; then the question that is not split has the row "Search query" and no "Found by" chips. Compare `app_decomposed_<platform>.png` with `$V gallery decompose pages/chat/diagnostics-decomposed.html <platform>`, and `app_decomposed_cards_<platform>.png` with `gallery_decomposed_cards_<platform>.png`. In the off run, the Chat page recipe's diagnostics flow still matches `diagnostics.html`.

## Gotchas

- The fake LLM splits on every " and ", also inside a clause, so pick questions whose parts have no "and" of their own.
- Ranks tie often with the fake embedder, so check `found_by` against the `fusion` lists in the same response, not against fixed IDs, except for a passage that only one sub-question's words reach.
- Expected differences from the gallery are those of the Chat page recipe: books, questions, numbers, scores and first words.
