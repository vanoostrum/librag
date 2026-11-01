# Copyright (C) 2026 Theo van Oostrum
"""The retrieval evaluation, run against the test app with the fakes.

The commands of `scripts/eval-fetch-books` and `scripts/eval-retrieval` run
in-process, with the test client as the stack and a worker tick as the wait.
The fixture set's books are tiny, with one passage per chapter, so the ranks
of BM25 and the fake reranker are known.
"""

import io
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update

from librag.db import books
from librag.epub import read_metadata
from librag.evaluation.cli import Io, main
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs

NOW = datetime(2026, 11, 1, 21, 30, tzinfo=UTC)


def _book(identifier: str, title: str, author: str, *texts: str) -> FixtureBook:
    return FixtureBook(
        identifier=identifier,
        title=title,
        author=author,
        chapters=tuple(
            FixtureChapter(paragraphs(text), nav_title=f"Part {n}")
            for n, text in enumerate(texts, start=1)
        ),
    )


SEA = _book(
    "urn:sea",
    "Sea Stories",
    "Ada Writer",
    "The lighthouse keeper polished the brass lamp every evening.",
    "Wild strawberries grew along the railway embankment.",
    "Gulls circled the old pier at noon.",
)
HARBOUR = _book(
    "urn:harbour",
    "Harbour Tales",
    "Ben Author",
    "A submarine captain charted the coral reef at dawn.",
    "The lighthouse beam swept across the harbour fog.",
)
# A book of the user's own, which the evaluation must never search or delete.
OWN = _book(
    "urn:own", "My Own Book", "Cy Owner", "The lighthouse keeper's own brass lamp."
)
SEA_ID = read_metadata(make_epub(SEA)).book_id
HARBOUR_ID = read_metadata(make_epub(HARBOUR)).book_id
OWN_ID = read_metadata(make_epub(OWN)).book_id

EVAL_SET = """
[books.sea]
gutenberg = 1
title = "Sea Stories"

[books.harbour]
gutenberg = 2
title = "Harbour Tales"

[[questions]]
id = "f1"
type = "factual"
question = "Who polished the brass lamp?"
evidence = [{ book = "sea", quote = "polished the brass lamp" }]

[[questions]]
id = "x1"
type = "cross-book"
question = "Which lighthouse is described?"
evidence = [
  { book = "sea", quote = "The lighthouse keeper polished" },
  { book = "harbour", quote = "the lighthouse beam swept" },
]

[[questions]]
id = "i1"
type = "indirect"
question = "Which fruits appeared beside rails?"
evidence = [{ book = "sea", quote = "Wild strawberries grew" }]

[[questions]]
id = "c1"
type = "conceptual"
question = "What did the submarine captain chart?"
books = ["harbour"]
authors = ["Ben Author"]
evidence = [{ book = "harbour", quote = "charted the coral reef" }]

[[questions]]
id = "n1"
type = "negative"
question = "Who won the chess championship?"
"""


@pytest.fixture
def eval_dir(tmp_path: Path) -> Path:
    """Return a folder with the fixture set and its EPUBs, as fetched."""
    books = tmp_path / "eval" / "books"
    books.mkdir(parents=True)
    (books / "pg1.epub").write_bytes(make_epub(SEA))
    (books / "pg2.epub").write_bytes(make_epub(HARBOUR))
    (tmp_path / "eval" / "retrieval.toml").write_text(EVAL_SET, encoding="utf-8")
    return tmp_path


@pytest.fixture
def requests(client: TestClient) -> Iterator[list[httpx2.Request]]:
    """Record each request that the test client sends."""
    sent: list[httpx2.Request] = []
    client.event_hooks["request"].append(sent.append)
    yield sent
    client.event_hooks["request"].remove(sent.append)


@pytest.fixture
def run(
    client: TestClient, work: Callable[[], bool], eval_dir: Path
) -> Callable[..., tuple[int, str, str]]:
    """Return a function that runs a command; it returns the code, out and err."""

    def run(
        *argv: str,
        http: httpx2.Client | None = None,
        gutenberg: httpx2.Client | None = None,
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        paths = [
            "--set",
            str(eval_dir / "eval" / "retrieval.toml"),
            "--books-dir",
            str(eval_dir / "eval" / "books"),
        ]
        if argv[0] == "run":
            paths += ["--reports-dir", str(eval_dir / "eval-reports")]

        def tick(_seconds: float) -> None:
            work()

        code = main(
            [*argv, *paths],
            Io(
                http=http or client,
                gutenberg=gutenberg,
                wait=tick,
                out=out,
                err=err,
                now=lambda: NOW,
            ),
        )
        return code, out.getvalue(), err.getvalue()

    return run


def library(client: TestClient) -> dict[str, str]:
    """Return the status of each book in the library, by book ID."""
    return {
        book["id"]: book["status"] for book in client.get("/api/books").json()["books"]
    }


def report(eval_dir: Path) -> dict[str, Any]:
    """Return the one JSON report of the run."""
    [path] = (eval_dir / "eval-reports").glob("retrieval-*.json")
    assert path.name == "retrieval-20261101T213000Z.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_fetch_uploads_the_books_and_waits_until_indexed(
    client: TestClient, run: Callable[..., tuple[int, str, str]]
) -> None:
    """`fetch` uploads each book of the set, and returns once all are indexed."""
    code, out, err = run("fetch")
    assert (code, err) == (0, "")
    assert "uploading Sea Stories" in out
    assert "uploading Harbour Tales" in out
    assert "All 2 evaluation books are indexed." in out
    assert library(client) == {SEA_ID: "indexed", HARBOUR_ID: "indexed"}


def test_run_reports_each_stage_and_deletes_the_books(
    client: TestClient,
    index: Callable[..., None],
    run: Callable[..., tuple[int, str, str]],
    requests: list[httpx2.Request],
    eval_dir: Path,
) -> None:
    """A run prints the metrics per stage, writes the JSON, then deletes its books.

    The user's own book stays, and no search reaches it.
    """
    index(OWN)
    code, out, err = run("run")
    assert (code, err) == (0, ""), err
    # The table: overall, per type, then the negatives.
    assert "All questions with evidence (4 questions)" in out
    assert "  stage       R@5   R@10   R@20    MRR" in out
    assert "Factual (1 questions)" in out
    assert "Negative questions: no book answers them; top rerank score" in out
    assert "n1                0.200  Who won the chess championship?" in out
    assert "Report: " in out

    body = report(eval_dir)
    stages = body["metrics"]["overall"]["stages"]
    # BM25 finds no word of i1 in any passage; the other questions' quotes are
    # in its first passages. Dense lists all 5 passages, so all are in the top 5.
    assert stages["bm25"]["recall@5"] == pytest.approx(0.75)
    assert stages["dense"]["recall@5"] == 1.0
    assert stages["fusion"]["recall@20"] == 1.0
    by_type = body["metrics"]["by_type"]
    assert set(by_type) == {"factual", "cross-book", "indirect", "conceptual"}
    assert by_type["indirect"]["stages"]["bm25"] == {
        "recall@5": 0.0,
        "recall@10": 0.0,
        "recall@20": 0.0,
        "mrr": 0.0,
    }
    for kind in ("factual", "cross-book", "conceptual"):
        assert by_type[kind]["stages"]["rerank"]["mrr"] == 1.0, kind
        assert by_type[kind]["stages"]["bm25"]["recall@5"] == 1.0, kind

    questions = {q["id"]: q for q in body["questions"]}
    assert questions["f1"]["first_relevant_rank"]["bm25"] == 1
    assert questions["f1"]["first_relevant_rank"]["rerank"] == 1
    assert questions["i1"]["first_relevant_rank"]["bm25"] is None
    assert {q["ranks"]["bm25"] for q in questions["x1"]["quotes"]} == {1, 2}
    assert questions["n1"]["quotes"] == []
    assert questions["n1"]["top_rerank_score"] == pytest.approx(0.2)
    assert body["missing_quotes"] == []
    assert body["search_settings"]["dense_k"] == 100  # noqa: PLR2004
    assert body["search_settings"]["embedding_model"] == "fake"
    assert body["library_books"] == 3  # noqa: PLR2004
    assert body["books"]["sea"]["index_configuration"] == {
        "passage_target_tokens": 350,
        "passage_overlap_tokens": 50,
        "tokenizer": "cl100k_base",
        "embedding_model": "fake",
    }

    searches = [
        json.loads(r.content) for r in requests if r.url.path == "/api/rag/search"
    ]
    assert len(searches) == 5  # noqa: PLR2004
    for search in searches:
        assert set(search["book_ids"]) <= {SEA_ID, HARBOUR_ID}
    c1 = next(s for s in searches if s["query"].startswith("What did"))
    assert c1["book_ids"] == [HARBOUR_ID]
    assert c1["authors"] == ["Ben Author"]
    assert library(client) == {OWN_ID: "indexed"}


def test_keep_books_leaves_them_for_the_next_run(
    client: TestClient, run: Callable[..., tuple[int, str, str]]
) -> None:
    """With --keep-books the books stay; the next run uploads nothing."""
    assert run("run", "--keep-books")[0] == 0
    assert library(client) == {SEA_ID: "indexed", HARBOUR_ID: "indexed"}
    code, out, _ = run("run")
    assert code == 0
    assert "uploading" not in out
    assert "Sea Stories is already in the library" in out
    assert "Harbour Tales is already in the library" in out
    # The run without --keep-books deletes the books that the evaluation added.
    assert library(client) == {}


def test_a_copy_already_in_the_library_is_used_and_kept(
    client: TestClient,
    index: Callable[..., None],
    run: Callable[..., tuple[int, str, str]],
) -> None:
    """A book of the set that the user added is not uploaded, nor deleted."""
    index(SEA)
    code, out, _ = run("run")
    assert code == 0
    assert "Sea Stories is already in the library" in out
    assert library(client) == {SEA_ID: "indexed"}


def test_quote_that_no_passage_holds_is_listed(
    run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """A quote that is not in its book is listed in the table and the JSON."""
    path = eval_dir / "eval" / "retrieval.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Wild strawberries grew", "Wild raspberries grew"
        ),
        encoding="utf-8",
    )
    code, out, _ = run("run")
    assert code == 0
    assert "Evidence quotes that no passage contains (fix the set):" in out
    assert "  i1: [sea] Wild raspberries grew" in out
    assert report(eval_dir)["missing_quotes"] == [
        {"question": "i1", "book": "sea", "quote": "Wild raspberries grew"}
    ]


def test_unreachable_stack_fails_with_a_clear_message(
    run: Callable[..., tuple[int, str, str]],
) -> None:
    """When the stack does not answer, the command says so and how to start it."""

    def refuse(request: httpx2.Request) -> httpx2.Response:
        message = "Connection refused"
        raise httpx2.ConnectError(message, request=request)

    http = httpx2.Client(
        base_url="http://localhost:8000", transport=httpx2.MockTransport(refuse)
    )
    code, _, err = run("run", http=http)
    assert code == 1
    assert err.startswith(
        "eval: the stack at http://localhost:8000 is not reachable "
        "(Connection refused)."
    )
    assert "docker compose up -d --wait" in err


def test_book_that_fails_to_index_stops_the_run(
    client: TestClient, run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """A book that fails to index stops the run with its error."""
    (eval_dir / "eval" / "books" / "pg2.epub").write_bytes(
        make_epub(_book("urn:harbour", "Harbour Tales", "Ben Author", ""))
    )
    code, _, err = run("run")
    assert code == 1
    assert (
        "Harbour Tales is not indexed: it failed with 'No text found in the EPUB'"
        in err
    )
    assert not (eval_dir / "eval-reports").exists()
    del client


def test_author_filter_that_matches_no_book_is_refused(
    run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """A question whose author filter names no evaluation book stops the run."""
    path = eval_dir / "eval" / "retrieval.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"Ben Author"', '"Ben Writer"'),
        encoding="utf-8",
    )
    code, _, err = run("run")
    assert code == 1
    assert "question c1: no evaluation book is by 'Ben Writer'" in err


def test_invalid_set_is_refused_before_any_upload(
    client: TestClient, run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """An evaluation set with a fault stops the command and names the question."""
    path = eval_dir / "eval" / "retrieval.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('type = "indirect"', 'type = "odd"'),
        encoding="utf-8",
    )
    code, _, err = run("fetch")
    assert code == 1
    assert err.startswith("eval: question i1: unknown type 'odd'")
    assert library(client) == {}


def _gutenberg(served: dict[str, bytes]) -> httpx2.Client:
    """Return a client for a fake Project Gutenberg that serves `served` by path."""

    def serve(request: httpx2.Request) -> httpx2.Response:
        if request.url.path in served:
            return httpx2.Response(HTTPStatus.OK, content=served[request.url.path])
        return httpx2.Response(HTTPStatus.NOT_FOUND)

    return httpx2.Client(
        base_url="https://www.gutenberg.org", transport=httpx2.MockTransport(serve)
    )


def test_missing_epub_is_downloaded_from_gutenberg(
    client: TestClient, run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """A book whose EPUB is not in the books folder is downloaded first."""
    epub = eval_dir / "eval" / "books" / "pg2.epub"
    epub.unlink()
    gutenberg = _gutenberg({"/ebooks/2.epub3.images": make_epub(HARBOUR)})
    code, out, _ = run("fetch", gutenberg=gutenberg)
    assert code == 0
    assert "downloading Harbour Tales (Project Gutenberg #2)" in out
    assert epub.read_bytes() == make_epub(HARBOUR)
    assert library(client)[HARBOUR_ID] == "indexed"


def test_failed_download_stops_with_the_status(
    run: Callable[..., tuple[int, str, str]], eval_dir: Path
) -> None:
    """A download that Project Gutenberg refuses stops the command."""
    (eval_dir / "eval" / "books" / "pg2.epub").unlink()
    code, _, err = run("fetch", gutenberg=_gutenberg({}))
    assert code == 1
    assert err.startswith(
        "eval: could not download Harbour Tales from Project Gutenberg: 404"
    )
    assert not (eval_dir / "eval" / "books" / "pg2.epub").exists()


def test_book_indexed_with_another_model_stops_the_run(
    engine: Engine, run: Callable[..., tuple[int, str, str]]
) -> None:
    """A book indexed with another embedding model than search uses is refused."""
    assert run("fetch")[0] == 0
    with engine.begin() as connection:
        connection.execute(
            update(books).where(books.c.id == SEA_ID).values(embedding_model="old")
        )
    code, _, err = run("run")
    assert code == 1
    assert (
        "eval: Sea Stories is indexed with old, but search embeds with fake. "
        "Reindex it, then run again." in err
    )
