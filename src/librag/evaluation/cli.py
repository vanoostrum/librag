# Copyright (C) 2026 Theo van Oostrum
"""The commands of `scripts/eval-fetch-books` and `scripts/eval-retrieval`.

`fetch` makes the books of the set indexed on the stack. `run` does that too,
runs every question through `POST /api/rag/search`, scores each stage, prints
the table and writes `eval-reports/retrieval-<timestamp>.json`. Then it
deletes the books it uploaded, unless `--keep-books` is given.
"""

import argparse
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import httpx2

from librag.epub import read_chapters
from librag.evaluation.evalset import EvalBook, EvalSet, EvalSetError, Question, load
from librag.evaluation.evalset import missing_quotes as find_missing
from librag.evaluation.report import report_json, table
from librag.evaluation.score import metrics, score_question
from librag.evaluation.stack import (
    GUTENBERG_URL,
    EvalError,
    Stack,
    delete_uploaded,
    download,
    ensure_books,
    epub_path,
)
from librag.passages import build_passages

DEFAULT_URL = "http://localhost:8000"
CANDIDATES_PER_STAGE = 100


@dataclass(frozen=True)
class Io:
    """What the commands talk to; the tests replace each part."""

    http: httpx2.Client | None = None
    gutenberg: httpx2.Client | None = None
    wait: Callable[[float], None] = time.sleep
    out: TextIO = sys.stdout
    err: TextIO = sys.stderr
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librag.evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("fetch", "Download the books of the set and index them on the stack."),
        ("run", "Run the evaluation set through search and report each stage."),
    ):
        command = commands.add_parser(name, help=text, description=text)
        command.add_argument("--set", type=Path, default=Path("eval/retrieval.toml"))
        command.add_argument("--books-dir", type=Path, default=Path("eval/books"))
    run = commands.choices["run"]
    run.add_argument(
        "--keep-books",
        action="store_true",
        help="Keep the evaluation books in the library after the run.",
    )
    run.add_argument("--reports-dir", type=Path, default=Path("eval-reports"))
    return parser


def _search_body(question: Question, ids: Mapping[str, str]) -> dict[str, Any]:
    keys = question.books or list(ids)
    return {
        "query": question.question,
        "dense_k": CANDIDATES_PER_STAGE,
        "bm25_k": CANDIDATES_PER_STAGE,
        "fusion_k": CANDIDATES_PER_STAGE,
        "rerank": True,
        # Only the evaluation books, so the rest of the library never shows up.
        "book_ids": [ids[key] for key in keys],
        "authors": list(question.authors),
    }


def _check_filters(evalset: EvalSet, books: Mapping[str, Mapping[str, Any]]) -> None:
    authors = {entry["author"] for entry in books.values()}
    for question in evalset.questions:
        unknown = [author for author in question.authors if author not in authors]
        if unknown:
            msg = (
                f"question {question.id}: no evaluation book is by '{unknown[0]}'; "
                f"the authors are {', '.join(sorted(a for a in authors if a))}"
            )
            raise EvalError(msg)


def _check_models(
    evalset: EvalSet, books: Mapping[str, Mapping[str, Any]], model: str
) -> None:
    for key, entry in books.items():
        indexed_with = entry["index_configuration"]["embedding_model"]
        if indexed_with != model:
            msg = (
                f"{evalset.books[key].title} is indexed with {indexed_with}, but "
                f"search embeds with {model}. Reindex it, then run again."
            )
            raise EvalError(msg)


def _passage_texts(
    evalset: EvalSet, books_dir: Path, books: Mapping[str, Mapping[str, Any]]
) -> dict[str, list[str]]:
    """Return the passages of each book, cut as its index configuration cuts them."""
    texts: dict[str, list[str]] = {}
    for key, book in evalset.books.items():
        config = books[key]["index_configuration"]
        chapters = read_chapters(epub_path(books_dir, book).read_bytes())
        passages = build_passages(
            chapters,
            config["passage_target_tokens"],
            config["passage_overlap_tokens"],
        )
        texts[key] = [passage.text for passage in passages]
    return texts


def _evaluate(
    stack: Stack,
    evalset: EvalSet,
    args: argparse.Namespace,
    books: Mapping[str, Mapping[str, Any]],
    io: Io,
) -> None:
    ids = {key: entry["id"] for key, entry in books.items()}
    _check_filters(evalset, books)
    missing = find_missing(evalset, _passage_texts(evalset, args.books_dir, books))
    scored = []
    settings: dict[str, Any] = {}
    for question in evalset.questions:
        body = stack.search(_search_body(question, ids))
        if not settings:
            settings = body["settings"]
            _check_models(evalset, books, settings["embedding_model"])
        scored.append(score_question(question, body, ids))
    result = metrics(scored)
    started = io.now()
    run = {
        "created_at": started.isoformat(),
        "url": stack.url,
        "evaluation_set": str(args.set),
        "search_settings": settings,
        "books": {
            key: {
                "book_id": entry["id"],
                "title": entry["title"],
                "author": entry["author"],
                "gutenberg": evalset.books[key].gutenberg,
                "index_configuration": entry["index_configuration"],
            }
            for key, entry in books.items()
        },
        # BM25 weighs words by their rarity in the whole collection, so the
        # rest of the library shifts its scores a little.
        "library_books": len(stack.books()),
    }
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    path = args.reports_dir / f"retrieval-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(
        json.dumps(report_json(result, scored, missing, run), indent=2) + "\n",
        encoding="utf-8",
    )
    print(table(result, scored, missing), file=io.out)
    print(f"\nReport: {path}", file=io.out)


def _fetcher(io: Io) -> Callable[[EvalBook, Path], None]:
    def fetch(book: EvalBook, path: Path) -> None:
        gutenberg = io.gutenberg or httpx2.Client(base_url=GUTENBERG_URL)
        download(gutenberg, book, path)

    return fetch


def main(argv: Sequence[str], io: Io | None = None) -> int:
    """Run the command in `argv`; return the exit code."""
    io = io or Io()
    args = _parser().parse_args(argv)
    url = os.environ.get("LIBRAG_EVAL_URL", DEFAULT_URL).rstrip("/")
    # The rerank of 100 candidates can take a while on a CPU.
    http = io.http or httpx2.Client(base_url=url, timeout=300.0)
    stack = Stack(http, url, wait=io.wait, log=lambda line: print(line, file=io.out))
    try:
        evalset = load(args.set)
        books = ensure_books(stack, evalset, args.books_dir, _fetcher(io))
        if args.command == "fetch":
            print(f"All {len(books)} evaluation books are indexed.", file=io.out)
            return 0
        try:
            _evaluate(stack, evalset, args, books, io)
        finally:
            if not args.keep_books:
                delete_uploaded(stack, args.books_dir)
    except (EvalError, EvalSetError) as error:
        print(f"eval: {error}", file=io.err)
        return 1
    return 0
