# Chat

A client asks a question with `POST /api/chat` and gets an answer from the library, in parts: `book` claims that cite passages, a `synthesis`, and `general` knowledge. The server checks every citation against the context that search selected, so a claim never shows as coming from the books without a passage from the context. With earlier turns, the LLM first rewrites the question into a standalone search query. Each request adds a row to the `chat_usage` table with its model, search query, tokens, cost and latency. `GET /api/config/models` lists the models chat can answer with. The stack uses the fake LLM: its answer cites context passages 1 and 2 in one book part and adds a synthesis part, and its rewrite appends the last turn's question to the question.

## Sub-features

- `chat-answer` returns 200 with `{"question", "search_query", "model", "parts", "citations", "usage", "retrieval"}`. Each part is `{"kind", "text", "citations": [n]}`, in the order book claims, synthesis, general. Each entry of `citations` is `{"n", "passage_id", "book_id", "title", "author", "chapter", "section", "text"}`, numbered 1, 2, … in the order the answer first cites it, and holds only cited passages. `usage` is `{"input_tokens", "output_tokens", "cost_usd", "latency_ms"}`; `retrieval` is the search response's `stages` and `settings`.
- `chat-no-passage` with no indexed book, or a filter that matches none: one `general` part that starts with "Your books hold no passage on this.", and `citations` is `[]`.
- `chat-rewrite` with `turns`: `search_query` is the rewritten question. With `LIBRAG_QUERY_REWRITE=off`, or without turns, it is the question. Only the last 3 turns are used.
- `chat-filters` with `book_ids` or `authors`: every citation is from those books or authors.
- `chat-usage` adds one `chat_usage` row per request that reaches the LLM, with the values of `usage`. A failed request is logged with its `error`.
- `chat-invalid` returns 422 with `{"error": "<field>: <what is wrong>"}` for a missing, empty or blank `question`, and for a `model` that is not in `LIBRAG_CHAT_MODELS`. A provider error, or an answer that is not valid JSON twice, returns 502 with `{"error"}`.
- `chat-models` returns 200 with `{"models": [{"id", "name", "default"}]}`: Claude Sonnet 5.5 (`anthropic/claude-sonnet-5-5`) as the default, and GPT 6.1 Terra (`openai/gpt-6.1-terra`).

## How to get to it (user POV)

- Upload books with `POST /api/books` and wait until `GET /api/books` shows them in `indexed`.
- Send `POST /api/chat` with a JSON body. Only `question` is required; `turns`, `model`, `book_ids` and `authors` are optional.
- Send `GET /api/config/models` for the model list.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.
- The library is empty. If an earlier recipe uploaded books, reset the library as the README says.

Set up the fixtures and the commands once:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/chat && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
DB=.verify/$LIBRAG_VERIFY_RUN/run/data/librag.db
uv run python -c "
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
def book(identifier, title, author, *texts):
    return FixtureBook(identifier=identifier, title=title, author=author, chapters=tuple(
        FixtureChapter(paragraphs(t), nav_title=f'Part {n}') for n, t in enumerate(texts, 1)))
d = '$E'
open(f'{d}/sea.epub', 'wb').write(make_epub(book('urn:sea', 'Sea Stories', 'Ada Writer',
    'The lighthouse keeper polished the brass lamp every evening.',
    'Wild strawberries grew along the railway embankment.')))
open(f'{d}/harbour.epub', 'wb').write(make_epub(book('urn:harbour', 'Harbour Tales', 'Ben Author',
    'A submarine captain charted the coral reef at dawn.',
    'The lighthouse beam swept across the harbour fog.')))
"
post() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -F "file=@$1" $URL/api/books | tee $E/$2.txt; }
ask() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -H 'content-type: application/json' -d "$1" $URL/api/chat | tee $E/$2.txt; }
usage() { uv run python -c "import sqlite3; [print(r) for r in sqlite3.connect('$DB').execute('select model, search_query, input_tokens, output_tokens, cost_usd, latency_ms, error from chat_usage order by id')]" | tee $E/usage.txt; }
```

`usage` reads the database file of process mode. In compose mode the database is in the `data` volume: run the same query with `docker compose -p librag-verify-$LIBRAG_VERIFY_RUN exec api python -c ...` and the path in `LIBRAG_DATABASE_URL`.

- **Models.** Run `$V get chat /api/config/models`. Status is `200`, the body is `{"models":[{"id":"anthropic/claude-sonnet-5-5","name":"Claude Sonnet 5.5","default":true},{"id":"openai/gpt-6.1-terra","name":"GPT 6.1 Terra","default":false}]}`.
- **No passage.** Run `ask '{"question":"Who built the first lighthouse?"}' no-passage`. Status is `200`; `parts` is one `general` part whose text starts with "Your books hold no passage on this.", and `citations` is `[]`.
- **Index.** Run `post $E/sea.epub upload-sea` and `post $E/harbour.epub upload-harbour`, wait 3 seconds, then `$V get chat /api/books`. Both books are in `indexed`.
- **Answer.** Run `ask '{"question":"lighthouse keeper brass lamp"}' answer`. Status is `200`; `model` is `anthropic/claude-sonnet-5-5`, `search_query` equals the question, `parts` is a `book` part with `citations` `[1,2]` and a `synthesis` part. `citations` has `n` 1 and 2; entry 1 is the Sea Stories keeper passage, with `chapter` `"Part 1"`. Each cited `passage_id` is in `retrieval.stages.rerank.passages`.
- **Rewrite.** Run `ask '{"question":"And the fog?","turns":[{"question":"What did the keeper polish?","answer":"The brass lamp."}]}' rewrite`. `search_query` is `"And the fog? What did the keeper polish?"`.
- **Filters.** Run `ask '{"question":"lighthouse","authors":["Ben Author"]}' author`. Every citation has `author` `"Ben Author"`. With `"book_ids":["<sea id>"]` (`book`), every citation has that `book_id`.
- **Invalid.** Run `ask '{"question":"  "}' blank` and `ask '{"question":"x","model":"openai/gpt-4"}' unknown-model`. Both are `422`, with `{"error":"question: String should have at least 1 character"}` and `{"error":"model: 'openai/gpt-4' is not one of the chat models"}`.
- **Usage.** Run `usage`. There is one row per `200` request above, in order, with the model, the search query, the tokens and the latency of its response's `usage`, `cost_usd` `0.0`, and no `error`. The `422` requests added no row.

## Gotchas

- The fake LLM ignores the model, so both models give the same answer. The provider error and invalid JSON paths need a real or scripted LLM; the route tests cover them.
- The fake LLM counts a word as a token and costs 0. A live model's cost is null when LiteLLM has no price for it.
- Citation numbers are renumbered in the order of the answer, so `n` is not the passage's rank in search.
- A book that is still `queued`, `parsing` or `indexing` is not searched. Poll `GET /api/books` before you ask.
