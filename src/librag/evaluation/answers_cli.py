# Copyright (C) 2026 Theo van Oostrum
"""The commands of `scripts/eval-answers`: run, grade and summary.

`run` asks every question of the evaluation set on each chat model through
`POST /api/chat`, and writes `eval-reports/answers-<timestamp>.json`. `grade`
serves the grading page for a report. `summary` prints, per model, the
grades, the evidence checks and the Ragas scores. See docs/answer-evaluation.md.
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import httpx2
from fastapi import FastAPI

from librag.evaluation.answers import AnswerRun
from librag.evaluation.evalset import EvalBook, EvalSet, EvalSetError, load
from librag.evaluation.grades import GradeStore, latest_report
from librag.evaluation.grading import create_grading_app
from librag.evaluation.judge import JUDGE_MODEL, Judge, RagasJudge
from librag.evaluation.stack import (
    GUTENBERG_URL,
    EvalError,
    Stack,
    delete_uploaded,
    download,
    ensure_books,
)
from librag.evaluation.summary import summary, text
from librag.evaluation.usage import budget_usd, missing_keys

DEFAULT_URL = "http://localhost:8000"
GRADING_HOST = "127.0.0.1"
GRADING_PORT = 8010
GRADES_FILE = "grades.json"


def _serve(app: FastAPI, host: str, port: int) -> None:  # pragma: no cover - blocks
    import uvicorn  # noqa: PLC0415 - only the grade command serves

    uvicorn.run(app, host=host, port=port, log_level="warning")


def _open(url: str) -> None:  # pragma: no cover - opens a browser
    webbrowser.open(url)


@dataclass(frozen=True)
class Io:
    """What the commands talk to; the tests replace each part."""

    http: httpx2.Client | None = None
    gutenberg: httpx2.Client | None = None
    judge: Callable[[], Judge] = RagasJudge
    serve: Callable[[FastAPI, str, int], None] = _serve
    open_browser: Callable[[str], None] = _open
    environ: Mapping[str, str] | None = None
    wait: Callable[[float], None] = time.sleep
    out: TextIO = sys.stdout
    err: TextIO = sys.stderr
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scripts/eval-answers")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Ask the evaluation set through chat on each chat model."
    )
    run.add_argument("--set", type=Path, default=Path("eval/retrieval.toml"))
    run.add_argument("--books-dir", type=Path, default=Path("eval/books"))
    run.add_argument(
        "--keep-books",
        action="store_true",
        help="Keep the evaluation books in the library after the run.",
    )
    run.add_argument(
        "--ragas",
        action="store_true",
        help=f"Score each answer with Ragas, judged by {JUDGE_MODEL}.",
    )
    grade = commands.add_parser("grade", help="Serve the grading page for a report.")
    grade.add_argument("--port", type=int, default=GRADING_PORT)
    grade.add_argument(
        "--no-browser", action="store_true", help="Do not open the page."
    )
    summarize = commands.add_parser(
        "summary", help="Print the grades, checks and Ragas scores per model."
    )
    for command in (grade, summarize):
        command.add_argument(
            "report", nargs="?", type=Path, help="The report; the latest by default."
        )
    for command in (run, grade, summarize):
        command.add_argument("--reports-dir", type=Path, default=Path("eval-reports"))
    return parser


def _report_path(args: argparse.Namespace) -> Path:
    if args.report is not None:
        if not args.report.exists():
            msg = f"there is no report at {args.report}"
            raise EvalError(msg)
        return Path(args.report)
    path = latest_report(args.reports_dir)
    if path is None:
        msg = (
            f"there is no answers report in {args.reports_dir}. "
            "Run `scripts/eval-answers run` first."
        )
        raise EvalError(msg)
    return path


def _fetcher(io: Io) -> Callable[[EvalBook, Path], None]:
    def fetch(book: EvalBook, path: Path) -> None:
        gutenberg = io.gutenberg or httpx2.Client(base_url=GUTENBERG_URL)
        download(gutenberg, book, path)

    return fetch


def _check_keys(
    models: Sequence[str], environ: Mapping[str, str], *, ragas: bool
) -> None:
    needed = [*models, JUDGE_MODEL] if ragas else list(models)
    missing = missing_keys(needed, environ)
    if missing:
        msg = (
            f"set {' and '.join(missing)} in your shell first. The run asks "
            f"{', '.join(models)} with your own keys"
            + (f", and {JUDGE_MODEL} judges for Ragas" if ragas else "")
            + ". See docs/answer-evaluation.md."
        )
        raise EvalError(msg)


def _write_report(
    args: argparse.Namespace,
    evalset_run: AnswerRun,
    started: datetime,
    stopped: str | None,
    budget: float,
) -> Path:
    report = {
        "created_at": started.isoformat(),
        "url": evalset_run.stack.url,
        "evaluation_set": str(args.set),
        "models": list(evalset_run.models),
        "ragas": args.ragas,
        "judge_model": JUDGE_MODEL if args.ragas else None,
        "stopped": stopped,
        "books": {
            key: {
                "book_id": entry["id"],
                "title": entry["title"],
                "author": entry["author"],
            }
            for key, entry in evalset_run.books.items()
        },
        "answers": evalset_run.answers,
        "usage": evalset_run.usage.report(budget),
    }
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    path = Path(args.reports_dir) / f"answers-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def _run(stack: Stack, evalset: EvalSet, args: argparse.Namespace, io: Io) -> int:
    environ = io.environ if io.environ is not None else os.environ
    try:
        budget = budget_usd(environ)
    except ValueError as error:
        raise EvalError(str(error)) from None
    models = stack.chat_models()
    _check_keys(models, environ, ragas=args.ragas)
    started = io.now()
    try:
        books = ensure_books(stack, evalset, args.books_dir, _fetcher(io))
        answer_run = AnswerRun(
            stack=stack,
            evalset=evalset,
            books=books,
            models=models,
            budget=budget,
            judge=io.judge() if args.ragas else None,
            log=lambda line: print(line, file=io.out),
        )
        stopped = answer_run.run()
        path = _write_report(args, answer_run, started, stopped, budget)
    finally:
        if not args.keep_books:
            _clean_up(stack, args.books_dir, io)
    print(file=io.out)
    print(answer_run.usage.table(budget), file=io.out)
    print(f"\nReport: {path}", file=io.out)
    if stopped is not None:
        print(
            f"eval: the run stopped early and saved "
            f"{len(answer_run.answers)} answers: {stopped}",
            file=io.err,
        )
        return 1
    return 0


def _clean_up(stack: Stack, books_dir: Path, io: Io) -> None:
    """Delete the books the run uploaded, also when the run failed."""
    try:
        delete_uploaded(stack, books_dir)
    except EvalError as error:
        # A book still indexing cannot be deleted yet; the next run tries again.
        print(f"eval: {error}. The next run deletes it.", file=io.err)


def _grade(args: argparse.Namespace, io: Io) -> int:
    path = _report_path(args)
    store = GradeStore(args.reports_dir / GRADES_FILE)
    app = create_grading_app(path, store)
    url = f"http://{GRADING_HOST}:{args.port}/"
    print(f"Grading {path} at {url} (Ctrl+C stops it)", file=io.out)
    if not args.no_browser:
        io.open_browser(url)
    io.serve(app, GRADING_HOST, args.port)
    return 0


def _summary(args: argparse.Namespace, io: Io) -> int:
    path = _report_path(args)
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    grades = GradeStore(args.reports_dir / GRADES_FILE).all()
    print(text(path.name, summary(report, grades, path.name)), file=io.out)
    return 0


def main(argv: Sequence[str], io: Io | None = None) -> int:
    """Run the command in `argv`; return the exit code."""
    io = io or Io()
    args = _parser().parse_args(argv)
    try:
        if args.command == "grade":
            return _grade(args, io)
        if args.command == "summary":
            return _summary(args, io)
        url = os.environ.get("LIBRAG_EVAL_URL", DEFAULT_URL).rstrip("/")
        # An answer can take a minute with a large model.
        http = io.http or httpx2.Client(base_url=url, timeout=300.0)
        stack = Stack(
            http, url, wait=io.wait, log=lambda line: print(line, file=io.out)
        )
        return _run(stack, load(args.set), args, io)
    except (EvalError, EvalSetError) as error:
        print(f"eval: {error}", file=io.err)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
