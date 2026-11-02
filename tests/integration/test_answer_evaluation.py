# Copyright (C) 2026 Theo van Oostrum
"""The answer evaluation, run against the test app with the fakes.

`scripts/eval-answers run` and `summary` run in-process, with the test client
as the stack, a worker tick as the wait, and a fake Ragas judge. The grading
page is tested through its routes.
"""

import io
import json
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from librag.evaluation.answers_cli import Io, main
from librag.evaluation.judge import Judgement
from tests.epubs import FixtureBook, FixtureChapter, make_epub, paragraphs
from tests.integration.test_evaluation import (
    EVAL_SET,
    HARBOUR,
    HARBOUR_ID,
    OWN,
    OWN_ID,
    SEA,
    SEA_ID,
)

NOW = datetime(2026, 11, 2, 16, 0, tzinfo=UTC)
MODELS = ["anthropic/claude-sonnet-5-5", "openai/gpt-6.1-terra"]
KEYS = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "sk-ant-test"}
QUESTIONS = ["f1", "x1", "i1", "c1", "n1"]


class FakeJudge:
    """Scores every answer 0.8 and 0.6, at a fixed cost, and records the calls."""

    model = "openai/gpt-6.1-terra"

    def __init__(self, cost_usd: float | None = 0.01) -> None:
        """Charge `cost_usd` per answer."""
        self.cost_usd = cost_usd
        self.calls: list[tuple[str, str, list[str]]] = []

    def judge(self, question: str, answer: str, contexts: Sequence[str]) -> Judgement:
        """Record the call and return fixed scores."""
        self.calls.append((question, answer, list(contexts)))
        return Judgement(
            faithfulness=0.8,
            answer_relevancy=0.6,
            input_tokens=100,
            output_tokens=10,
            cost_usd=self.cost_usd,
            latency_ms=5.0,
        )


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


Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(client: TestClient, work: Callable[[], bool], eval_dir: Path) -> Run:
    """Return a function that runs a command; it returns the code, out and err."""

    def run(  # noqa: PLR0913 - each keyword replaces one part of Io
        *argv: str,
        environ: dict[str, str] | None = None,
        judge: FakeJudge | None = None,
        http: httpx2.Client | None = None,
        now: datetime = NOW,
        served: list[tuple[FastAPI, str, int]] | None = None,
        opened: list[str] | None = None,
    ) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        paths = ["--reports-dir", str(eval_dir / "eval-reports")]
        if argv[0] == "run":
            paths += [
                "--set",
                str(eval_dir / "eval" / "retrieval.toml"),
                "--books-dir",
                str(eval_dir / "eval" / "books"),
            ]

        def no_judge() -> FakeJudge:
            pytest.fail("the run made a Ragas judge without --ragas")

        def tick(_seconds: float) -> None:
            work()

        servings = served if served is not None else []
        openings = opened if opened is not None else []

        code = main(
            [*argv, *paths],
            Io(
                http=http or client,
                judge=(lambda: judge) if judge else no_judge,
                serve=lambda app, host, port: servings.append((app, host, port)),
                open_browser=openings.append,
                environ=KEYS if environ is None else environ,
                wait=tick,
                out=out,
                err=err,
                now=lambda: now,
            ),
        )
        return code, out.getvalue(), err.getvalue()

    return run


def library(client: TestClient) -> dict[str, str]:
    """Return the status of each book in the library, by book ID."""
    return {
        book["id"]: book["status"] for book in client.get("/api/books").json()["books"]
    }


def report(eval_dir: Path, when: datetime = NOW) -> dict[str, Any]:
    """Return the JSON report that a run at `when` wrote."""
    path = eval_dir / "eval-reports" / f"answers-{when:%Y%m%dT%H%M%SZ}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def answers(body: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Return the report's answers by question ID and model."""
    return {(a["question_id"], a["model"]): a for a in body["answers"]}


def test_run_asks_every_question_on_each_model_and_writes_the_report(
    client: TestClient,
    index: Callable[..., None],
    run: Run,
    requests: list[httpx2.Request],
    eval_dir: Path,
) -> None:
    """A run asks each question on both models, only over the evaluation books.

    It writes the report, prints the usage table, and deletes its books; the
    user's own book stays and is never asked.
    """
    index(OWN)
    code, out, err = run("run")
    assert (code, err) == (0, ""), err

    chats = [json.loads(r.content) for r in requests if r.url.path == "/api/chat"]
    assert [(c["question"][:8], c["model"]) for c in chats[:2]] == [
        ("Who poli", MODELS[0]),
        ("Who poli", MODELS[1]),
    ]
    assert len(chats) == len(QUESTIONS) * len(MODELS)
    for chat in chats:
        assert set(chat["book_ids"]) <= {SEA_ID, HARBOUR_ID}
    c1 = next(c for c in chats if c["question"].startswith("What did"))
    assert c1["book_ids"] == [HARBOUR_ID]
    assert c1["authors"] == ["Ben Author"]
    assert library(client) == {OWN_ID: "indexed"}

    body = report(eval_dir)
    assert body["models"] == MODELS
    assert body["ragas"] is False
    assert body["stopped"] is None
    assert set(body["books"]) == {"sea", "harbour"}
    assert {key for key, _ in answers(body)} == set(QUESTIONS)
    assert len(body["answers"]) == len(QUESTIONS) * len(MODELS)

    f1 = answers(body)["f1", MODELS[0]]
    assert f1["type"] == "factual"
    assert f1["question"] == "Who polished the brass lamp?"
    assert f1["parts"][0]["kind"] == "book"
    assert f1["parts"][0]["citations"] == [1, 2]
    first = f1["citations"][0]
    assert first["n"] == 1
    assert first["book"] == "sea"
    assert first["title"] == "Sea Stories"
    assert first["chapter"] == "Part 1"
    assert "polished the brass lamp" in first["text"]
    assert f1["evidence"] == {
        "passed": True,
        "quotes": [
            {"book": "sea", "quote": "polished the brass lamp", "cited_in": [1]}
        ],
    }
    assert set(f1["usage"]) == {
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
    }
    assert f1["usage"]["latency_ms"] >= 0
    assert len(f1["answer_hash"]) == 16  # noqa: PLR2004
    assert f1["ragas"] is None

    # The fake LLM claims from the books, so the negative question fails.
    n1 = answers(body)["n1", MODELS[1]]
    assert n1["evidence"] == {"passed": False, "book_claims": 1, "quotes": []}

    rows = {row["model"]: row for row in body["usage"]["models"]}
    assert rows[MODELS[0]]["requests"] == len(QUESTIONS)
    assert "model" in out
    assert "requests" in out
    assert "mean latency" in out
    assert f"{MODELS[0]}  " in out
    assert "known cost $0.0000 of the $2.00 cap" in out
    assert "Report: " in out


def test_evidence_check_says_which_quotes_were_not_cited(
    run: Run, eval_dir: Path
) -> None:
    """A quote that no cited passage holds has no `cited_in`, and fails the check."""
    assert run("run")[0] == 0
    # The fake LLM cites the first 2 passages of the context; for x1 the
    # harbour quote is in the second, the sea quote is in the first.
    x1 = answers(report(eval_dir))["x1", MODELS[0]]
    cited = {q["book"]: q["cited_in"] for q in x1["evidence"]["quotes"]}
    assert all(cited.values()) == x1["evidence"]["passed"]
    i1 = answers(report(eval_dir))["i1", MODELS[0]]
    texts = " ".join(c["text"] for c in i1["citations"])
    found = "Wild strawberries grew" in texts
    assert i1["evidence"]["passed"] is found
    assert bool(i1["evidence"]["quotes"][0]["cited_in"]) is found


@pytest.mark.parametrize(
    ("environ", "missing"),
    [
        ({}, "ANTHROPIC_API_KEY and OPENAI_API_KEY"),
        ({"OPENAI_API_KEY": "sk-test"}, "ANTHROPIC_API_KEY"),
        ({"ANTHROPIC_API_KEY": "sk-ant", "OPENAI_API_KEY": ""}, "OPENAI_API_KEY"),
    ],
)
def test_missing_key_refuses_to_start(
    client: TestClient,
    run: Run,
    requests: list[httpx2.Request],
    environ: dict[str, str],
    missing: str,
) -> None:
    """Without a key of a chat model's provider, the run starts nothing."""
    code, _, err = run("run", environ=environ)
    assert code == 1
    assert err.startswith(f"eval: set {missing} in your shell first.")
    assert [r.url.path for r in requests] == ["/api/config/models"]
    assert library(client) == {}


def test_ragas_needs_the_judge_key(client: TestClient, run: Run) -> None:
    """With --ragas, the judge's OpenAI key is needed too."""
    code, _, err = run(
        "run",
        "--ragas",
        environ={"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "sk-ant"},
        judge=FakeJudge(),
    )
    assert code == 1
    assert "set OPENAI_API_KEY in your shell first" in err
    assert "openai/gpt-6.1-terra judges for Ragas" in err
    assert library(client) == {}


def test_unreachable_stack_fails_with_a_clear_message(run: Run) -> None:
    """When the stack does not answer, the run says so and how to start it."""

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


def test_book_that_fails_to_index_stops_the_run(
    client: TestClient, run: Run, requests: list[httpx2.Request], eval_dir: Path
) -> None:
    """A book of the set that cannot be indexed stops the run before any chat."""
    (eval_dir / "eval" / "books" / "pg2.epub").write_bytes(
        make_epub(
            FixtureBook(
                identifier="urn:harbour",
                title="Harbour Tales",
                author="Ben Author",
                chapters=(FixtureChapter(paragraphs(""), nav_title="Part 1"),),
            )
        )
    )
    code, _, err = run("run")
    assert code == 1
    assert "Harbour Tales is not indexed: it failed with" in err
    assert not any(r.url.path == "/api/chat" for r in requests)
    assert not (eval_dir / "eval-reports").exists()
    assert library(client) == {}


def test_ragas_scores_each_answer_with_the_judge(run: Run, eval_dir: Path) -> None:
    """With --ragas, each answer gets faithfulness and answer relevancy.

    The judge gets the question, the answer's text, and the passages that the
    answer's prompt held. Its cost goes into the usage table.
    """
    judge = FakeJudge()
    code, out, err = run("run", "--ragas", judge=judge)
    assert (code, err) == (0, ""), err
    body = report(eval_dir)
    assert body["ragas"] is True
    assert body["judge_model"] == "openai/gpt-6.1-terra"
    for answer in body["answers"]:
        assert answer["ragas"] == {
            "faithfulness": 0.8,
            "answer_relevancy": 0.6,
            "judge_model": "openai/gpt-6.1-terra",
            "cost_usd": 0.01,
        }
    assert len(judge.calls) == len(QUESTIONS) * len(MODELS)
    question, answer, contexts = judge.calls[0]
    assert question == "Who polished the brass lamp?"
    assert answer.startswith("The fake LLM answers from the passages it cites.")
    assert any("polished the brass lamp" in text for text in contexts)
    assert "openai/gpt-6.1-terra (Ragas judge)" in out
    assert "known cost $0.1000 of the $2.00 cap" in out


def test_budget_stops_the_run_and_saves_what_it_has(run: Run, eval_dir: Path) -> None:
    """Once chat and Ragas together reach the cap, the run stops and saves."""
    code, out, err = run(
        "run",
        "--ragas",
        environ={**KEYS, "LIBRAG_LIVE_BUDGET_USD": "0.015"},
        judge=FakeJudge(cost_usd=0.01),
    )
    assert code == 1
    assert "eval: the run stopped early and saved 2 answers: budget reached" in err
    body = report(eval_dir)
    assert len(body["answers"]) == 2  # noqa: PLR2004
    assert body["stopped"].startswith("budget reached: the run's known cost is $0.0200")
    assert "known cost $0.0200 of the $0.01 cap" in out


def test_invalid_budget_is_refused(run: Run) -> None:
    """A budget that is not an amount stops the run before it starts."""
    code, _, err = run("run", environ={**KEYS, "LIBRAG_LIVE_BUDGET_USD": "lots"})
    assert code == 1
    assert "LIBRAG_LIVE_BUDGET_USD must be an amount in dollars" in err


def test_failed_chat_stops_the_run_and_saves_what_it_has(
    client: TestClient, run: Run, eval_dir: Path
) -> None:
    """A chat request that fails stops the run; the answers so far are saved."""
    calls = {"chat": 0}

    def fail_third(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/api/chat":
            calls["chat"] += 1
            if calls["chat"] == 3:  # noqa: PLR2004
                return httpx2.Response(
                    HTTPStatus.BAD_GATEWAY, json={"error": "The provider failed"}
                )
        response = client.request(
            request.method,
            request.url.path,
            content=request.content,
            headers=request.headers,
        )
        return httpx2.Response(
            response.status_code, content=response.content, headers=response.headers
        )

    http = httpx2.Client(
        base_url="http://testserver", transport=httpx2.MockTransport(fail_third)
    )
    code, _, err = run("run", http=http)
    assert code == 1
    assert "saved 2 answers: POST /api/chat failed with 502" in err
    assert len(report(eval_dir)["answers"]) == 2  # noqa: PLR2004
    assert library(client) == {}


# The grading page.


@pytest.fixture
def grading(run: Run) -> Callable[..., TestClient]:
    """Return a function that runs `grade` and returns a client for its page."""

    def grading(*argv: str) -> TestClient:
        served: list[tuple[FastAPI, str, int]] = []
        code, _, err = run("grade", *argv, "--no-browser", served=served)
        assert (code, err) == (0, ""), err
        [(app, host, port)] = served
        assert (host, port) == ("127.0.0.1", 8010)
        return TestClient(app)

    return grading


def _grades(eval_dir: Path) -> dict[str, Any]:
    path = eval_dir / "eval-reports" / "grades.json"
    return json.loads(path.read_text(encoding="utf-8"))["grades"]


def test_grade_serves_the_latest_report_and_opens_it(run: Run) -> None:
    """`grade` serves the newest report on 127.0.0.1:8010 and opens the page."""
    assert run("run", "--keep-books")[0] == 0
    later = NOW + timedelta(hours=1)
    assert run("run", now=later)[0] == 0
    served: list[tuple[FastAPI, str, int]] = []
    opened: list[str] = []
    code, out, _ = run("grade", served=served, opened=opened)
    assert code == 0
    assert opened == ["http://127.0.0.1:8010/"]
    assert f"answers-{later:%Y%m%dT%H%M%SZ}.json" in out
    page = TestClient(served[0][0]).get("/")
    assert f"answers-{later:%Y%m%dT%H%M%SZ}.json" in page.text


def test_page_shows_a_card_per_answer(
    run: Run, grading: Callable[..., TestClient]
) -> None:
    """The page has a card per question and model, with what grading needs."""
    assert run("run")[0] == 0
    page = grading()
    response = page.get("/")
    assert response.status_code == HTTPStatus.OK
    html = response.text
    assert html.count('<article class="card"') == len(QUESTIONS) * len(MODELS)
    assert '<link rel="stylesheet" href="/app.css">' in html
    assert "Who polished the brass lamp?" in html
    assert "The fake LLM answers from the passages it cites." in html
    assert "[1] Sea Stories · Part 1" in html
    assert "Evidence check:" in html
    assert "Negative question: 1 book claims." in html
    assert "Answer quality" in html
    assert "Partly correct" in html
    assert '<span id="to-grade">10</span> still to grade' in html
    css = page.get("/app.css")
    assert css.status_code == HTTPStatus.OK
    assert css.headers["content-type"].startswith("text/css")
    assert "--paper" in css.text

    cards = page.get("/api/cards").json()
    assert cards["to_grade"] == len(QUESTIONS) * len(MODELS)
    first = cards["cards"][0]
    assert first["needs_grade"] is True
    assert first["state"] == "Needs a grade"
    assert first["grade"] == {"quality": None, "citations": None, "notes": ""}
    assert {"question_id", "type", "model", "parts", "citations", "evidence"} <= set(
        first
    )


def test_grade_saves_at_once_and_a_reload_shows_it(
    run: Run, grading: Callable[..., TestClient], eval_dir: Path
) -> None:
    """Each choice saves to grades.json; a reload shows it, graded cards last."""
    assert run("run")[0] == 0
    page = grading()
    index = page.get("/api/cards").json()["cards"][0]["index"]

    response = page.put(f"/api/answers/{index}/grade", json={"quality": 4})
    assert response.status_code == HTTPStatus.OK
    assert response.json()["needs_grade"] is True
    saved = next(iter(_grades(eval_dir).values()))
    assert saved["quality"] == 4  # noqa: PLR2004
    assert saved["citations"] is None

    response = page.put(
        f"/api/answers/{index}/grade", json={"citations": "partly", "notes": "Thin."}
    )
    body = response.json()
    assert body["state"] == "Graded"
    assert body["to_grade"] == len(QUESTIONS) * len(MODELS) - 1
    assert body["grade"] == {"quality": 4, "citations": "partly", "notes": "Thin."}

    reloaded = page.get("/api/cards").json()["cards"]
    assert reloaded[-1]["index"] == index
    assert reloaded[-1]["grade"]["quality"] == 4  # noqa: PLR2004
    html = page.get("/").text
    assert 'value="partly"\n  checked' in html
    assert ">Thin.</textarea>" in html
    assert '<span id="to-grade">9</span> still to grade' in html


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"quality": 6}, "quality: must be a whole number from 1 to 5"),
        ({"citations": "fine"}, "citations: must be correct, partly or wrong"),
        ({"stars": 3}, "stars: not a grade field"),
        ([1], "The body must be a JSON object"),
    ],
)
def test_invalid_grade_is_refused(
    run: Run,
    grading: Callable[..., TestClient],
    eval_dir: Path,
    change: object,
    error: str,
) -> None:
    """An invalid grade gets a 422 and is not saved."""
    assert run("run")[0] == 0
    response = grading().put("/api/answers/0/grade", json=change)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": error}
    assert not (eval_dir / "eval-reports" / "grades.json").exists()


def test_body_that_is_not_json_is_refused(
    run: Run, grading: Callable[..., TestClient]
) -> None:
    """A grade body that is not JSON gets a 422."""
    assert run("run")[0] == 0
    response = grading().put("/api/answers/0/grade", content=b"quality=3")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {"error": "The body must be a JSON object"}


def test_unknown_answer_is_not_found(
    run: Run, grading: Callable[..., TestClient]
) -> None:
    """A grade for an answer number the report does not have gets a 404."""
    assert run("run")[0] == 0
    response = grading().put("/api/answers/99/grade", json={"quality": 3})
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_unchanged_answer_keeps_its_grade_in_a_later_run(
    run: Run, grading: Callable[..., TestClient], eval_dir: Path
) -> None:
    """An answer that reads and cites the same as a graded one is carried over.

    An answer that changed needs a new grade. Search orders tied passages in
    any order, so the test compares each answer's hash with the graded ones,
    and changes one answer of the second report by hand.
    """
    assert run("run", "--keep-books")[0] == 0
    first = grading()
    graded_hashes = set()
    for card in first.get("/api/cards").json()["cards"]:
        first.put(
            f"/api/answers/{card['index']}/grade",
            json={"quality": 5, "citations": "correct"},
        )
        graded_hashes.add((card["question_id"], card["model"], card["answer_hash"]))
    later = NOW + timedelta(hours=1)
    assert run("run", now=later)[0] == 0
    path = eval_dir / "eval-reports" / f"answers-{later:%Y%m%dT%H%M%SZ}.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    f1 = next(a for a in body["answers"] if a["question_id"] == "f1")
    f1["parts"][0]["text"] = "A new answer."
    f1["answer_hash"] = "0123456789abcdef"
    path.write_text(json.dumps(body), encoding="utf-8")

    page = grading(str(path))
    cards = page.get("/api/cards").json()["cards"]
    for card in cards:
        same = (
            card["question_id"],
            card["model"],
            card["answer_hash"],
        ) in graded_hashes
        assert card["carried_over"] is same, card["question_id"]
        assert card["needs_grade"] is not same, card["question_id"]
        assert card["state"] == ("Carried over" if same else "Needs a grade")
    assert sum(card["carried_over"] for card in cards) >= len(cards) // 2
    assert cards[0]["question_id"] == "f1"
    assert cards[0]["grade"] == {"quality": None, "citations": None, "notes": ""}
    assert "Carried over" in page.get("/").text


def test_grade_without_a_report_says_to_run_first(run: Run) -> None:
    """`grade` and `summary` need a report; without one they say how to make it."""
    for command in ("grade", "summary"):
        code, _, err = run(command)
        assert code == 1
        assert "there is no answers report in" in err
        assert "Run `scripts/eval-answers run` first." in err


def test_named_report_that_does_not_exist_is_refused(run: Run) -> None:
    """A report path that does not exist is refused."""
    code, _, err = run("summary", "nowhere.json")
    assert code == 1
    assert err == "eval: there is no report at nowhere.json\n"


# The summary.


def test_summary_prints_grades_checks_and_ragas_per_model(
    run: Run, grading: Callable[..., TestClient]
) -> None:
    """`summary` prints each model's grades, evidence checks, Ragas and agreement."""
    assert run("run", "--ragas", judge=FakeJudge())[0] == 0
    page = grading()
    for card in page.get("/api/cards").json()["cards"]:
        if card["model"] == MODELS[0] and card["question_id"] in {"f1", "x1"}:
            grade = {"quality": 4, "citations": "correct"}
            if card["question_id"] == "x1":
                grade = {"quality": 2, "citations": "wrong"}
            page.put(f"/api/answers/{card['index']}/grade", json=grade)

    code, out, err = run("summary")
    assert (code, err) == (0, ""), err
    lines = out.splitlines()
    assert lines[0] == f"Answer evaluation: answers-{NOW:%Y%m%dT%H%M%SZ}.json"
    first = lines[lines.index(MODELS[0]) : lines.index(MODELS[1])]
    assert "  answers              5 (3 still to grade, 0 carried over)" in first
    assert "  quality, mean (1-5)  3.00 over 2 graded" in first
    assert (
        "  citations            correct 50%, partly correct 0%, wrong 50% "
        "over 2 graded" in first
    )
    assert "  Ragas faithfulness   0.80 mean" in first
    assert "  Ragas relevancy      0.60 mean" in first
    # The fake judge gives every answer the same scores, so there is no spread.
    assert (
        "  Ragas agreement      faithfulness ~ citations none (n=2), "
        "relevancy ~ quality none (n=2)" in first
    )
    second = lines[lines.index(MODELS[1]) :]
    assert "  answers              5 (5 still to grade, 0 carried over)" in second
    assert "  quality, mean (1-5)  none over 0 graded" in second
    assert any(line.startswith("  evidence check       ") for line in second)
