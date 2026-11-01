# Search

A client sends a search query with `POST /api/rag/search` and gets the context, without the LLM: the fused candidates of hybrid retrieval, reranked, then cut to `top_k` passages within `token_budget` tokens. This is the context that chat will send to the LLM. The response shows each stage (dense, BM25, their RRF fusion, and the rerank) with its passage IDs, ranks, scores and time, and the limits it used. Only books in `indexed` are searched. The stack uses the fake reranker, which scores a passage by the share of the query's distinct words it contains.

## Sub-features

- `search-results` returns 200 with `{"query", "results", "stages", "settings"}`. Each result has `rank`, `passage_id`, `book_id`, `title`, `author`, `chapter`, `section`, `text`, `score`, `fusion_score` and `rerank_score`. `score` is the rerank score, or the fusion score when reranking is off. The passage that holds the most query words is first.
- `search-stages` has `stages.dense`, `stages.bm25`, `stages.fusion` and `stages.rerank`, each `{"passages": [{"passage_id", "rank", "score"}], "time_ms"}`. BM25 lists only passages that share a word with the query. The rerank stage lists every fused candidate. `results` follow the rerank order.
- `search-rerank-off` with `"rerank": false`: `results` follow the fusion order, every `rerank_score` is null, and `stages.rerank` is `{"passages": [], "time_ms": 0.0}`.
- `search-budget` skips a passage that does not fit the remaining `token_budget`, and still adds a later one that fits.
- `search-limits` caps `results` at `top_k` and `token_budget`, the dense stage at `dense_k`, BM25 at `bm25_k`, and fusion at `fusion_k`. Without them, the settings give 10, 4000, 30, 30 and 30 (`LIBRAG_SEARCH_TOP_K`, `LIBRAG_CONTEXT_TOKEN_BUDGET`, `LIBRAG_DENSE_TOP_K`, `LIBRAG_BM25_TOP_K`, `LIBRAG_FUSION_TOP_K`). `settings` in the response shows the values used, `rerank`, and the embedding and reranker models.
- `search-filters` limits the results and every stage to `book_ids` and to `authors`, as `GET /api/books` shows them. An empty list does not filter.
- `search-empty` returns 200 with empty `results` and stage lists when no book is indexed, or when a filter matches no indexed book.
- `search-invalid` returns 422 with `{"error": "<field>: <what is wrong>"}` for a missing, empty or blank `query`, for a `top_k`, `dense_k`, `bm25_k` or `fusion_k` outside 1 to 100, for a `token_budget` outside 100 to 32000, and for a `rerank` that is not a boolean.

## How to get to it (user POV)

- Upload books with `POST /api/books` and wait until `GET /api/books` shows them in `indexed`.
- Send `POST /api/rag/search` with a JSON body. Only `query` is required.

## Driving it with librag-verify

Preconditions:

- The baseline preconditions in the README hold.
- The library is empty. If an earlier recipe uploaded books, reset the library as the README says.

Set up the fixtures and the commands once:

```bash
E=.verify/$LIBRAG_VERIFY_RUN/evidence/search && mkdir -p $E
URL=http://127.0.0.1:$(cat .verify/$LIBRAG_VERIFY_RUN/run/port)
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
open(f'{d}/budget.epub', 'wb').write(make_epub(book('urn:budget', 'Budget', 'Ada Writer',
    ' '.join(['The lighthouse keeper lit the beacon and logged every ship.'] * 12),
    'Lighthouse beacon, lighthouse beacon: the lighthouse beacon on the cape.')))
"
post() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -F "file=@$1" $URL/api/books | tee $E/$2.txt; }
search() { curl -sS -D $E/$2.headers -w '\n%{http_code}\n' -H 'content-type: application/json' -d "$1" $URL/api/rag/search | tee $E/$2.txt; }
```

- **Empty library.** Run `search '{"query":"lighthouse"}' empty`. Status is `200`; `results` and each stage's `passages` are `[]`, and `settings` is `{"top_k":10,"dense_k":30,"bm25_k":30,"fusion_k":30,"token_budget":4000,"rerank":true,"embedding_model":"fake","reranker_model":"fake"}`.
- **Index.** Run `post $E/sea.epub upload-sea` and `post $E/harbour.epub upload-harbour`, wait 3 seconds, then `$V get search /api/books`. Both books are in `indexed`.
- **Best passage first.** Run `search '{"query":"lighthouse keeper brass lamp"}' best`. Status is `200`; the first result is the Sea Stories passage "The lighthouse keeper polished…", with `rank` 1, `chapter` `"Part 1"`, `section` null, and the first entry of each stage has its `passage_id`.
- **Both books.** Run `search '{"query":"lighthouse"}' both`. `results` hold passages from both books; `stages.bm25.passages` has exactly the two lighthouse passages.
- **Rerank.** Run `search '{"query":"lighthouse brass"}' rerank`. `stages.rerank.passages` lists every passage of `stages.fusion`; the keeper passage (both words) is first with score `1.0`, and the beam passage (one word) has `0.5`. `results` follow the rerank order, each with `fusion_score` and `rerank_score`.
- **Rerank off.** Run `search '{"query":"lighthouse brass","rerank":false}' rerank-off`. `results` follow `stages.fusion`, every `rerank_score` is null, and `stages.rerank` is `{"passages":[],"time_ms":0.0}`.
- **Limits.** Run `search '{"query":"lighthouse","top_k":1,"dense_k":2,"bm25_k":1,"fusion_k":2}' limits`. `results` has 1 entry, the dense stage 2, BM25 1, fusion at most 2, and `settings` shows `1`, `2`, `1`, `2`.
- **Budget.** Run `post $E/budget.epub upload-budget`, wait 3 seconds, and take the Budget book ID from `/api/books`. Its first passage is about 140 tokens, the second about 20. Run `search '{"query":"lighthouse beacon keeper","book_ids":["<budget id>"],"token_budget":100}' budget`: `stages.rerank` lists the long passage first, and `results` hold only the short one, with `rank` 1. With `"token_budget":1000` (`budget-room`), `results` hold both, long first.
- **Filters.** Run `search '{"query":"lighthouse","authors":["Ben Author"]}' author` and `search '{"query":"lighthouse","book_ids":["<sea id>"]}' book`, with the Sea Stories ID from `/api/books`. Every result and stage passage is from that author's or that book's passages only.
- **Unknown book.** Run `search '{"query":"lighthouse","book_ids":["0000000000000000"]}' unknown-book`. Status is `200` with empty lists.
- **Invalid.** Run `search '{"query":"  "}' blank` and `search '{"query":"x","top_k":101}' too-many`. Both are `422`, with `{"error":"query: String should have at least 1 character"}` and `{"error":"top_k: Input should be less than or equal to 100"}`. Also run `search '{"query":"x","token_budget":99}' small-budget`: `422`, with `{"error":"token_budget: Input should be greater than or equal to 100"}`.

## Gotchas

- The stack uses the fake embedder, which hashes words, so dense ranking only reflects shared words. Pick query words from the passage you expect first.
- Scores depend on Qdrant: check the order and the IDs, not exact scores.
- A book that is still `queued`, `parsing` or `indexing` is not searched. Poll `GET /api/books` before you search.
- Passage IDs are UUID5 of `<book id>/<position>`, so the same fixture always gets the same IDs.
