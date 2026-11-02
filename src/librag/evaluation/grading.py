# Copyright (C) 2026 Theo van Oostrum
"""The grading page: a small local app to grade the answers of one report.

`scripts/eval-answers grade` serves it on 127.0.0.1:8010. It is a developer
tool outside LibRag, so it has no gallery page; it borrows the app's
stylesheet for type and colour. Each grade is saved to `grades.json` at once.
"""

import json
from http import HTTPStatus
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from jinja2 import Environment, select_autoescape

from librag.evaluation.grades import (
    CITATION_GRADES,
    CITATION_LABELS,
    QUALITY_GRADES,
    GradeError,
    GradeStore,
    graded,
)

_STATES = {
    "needs": ("Needs a grade", "state--needs"),
    "graded": ("Graded", "state--graded"),
    "carried": ("Carried over", "state--carried"),
}


def _score(value: float | None) -> str:
    return "none" if value is None else f"{value:.2f}"


class Grading:
    """The cards of one report, with the grades in the store."""

    def __init__(self, report_path: Path, store: GradeStore) -> None:
        """Grade the answers of the report at `report_path` into `store`."""
        self.report_path = report_path
        self.name = report_path.name
        self.store = store
        self.answers: list[dict[str, Any]] = json.loads(
            report_path.read_text(encoding="utf-8")
        )["answers"]

    def card(self, index: int, grades: dict[str, Any]) -> dict[str, Any]:
        """Return the card of answer `index`, as the page and the JSON show it."""
        answer = self.answers[index]
        found = graded(grades, answer, self.name)
        if found.needs_grade:
            state = "needs"
        elif found.carried_over:
            state = "carried"
        else:
            state = "graded"
        ragas = answer.get("ragas")
        if ragas:
            ragas = {
                **ragas,
                "faithfulness_text": _score(ragas.get("faithfulness")),
                "answer_relevancy_text": _score(ragas.get("answer_relevancy")),
            }
        grade = found.grade or {}
        return {
            "index": index,
            **{
                key: answer[key]
                for key in (
                    "question_id",
                    "type",
                    "question",
                    "model",
                    "answer_hash",
                    "parts",
                    "citations",
                    "evidence",
                )
            },
            "ragas": ragas,
            "grade": {
                "quality": grade.get("quality"),
                "citations": grade.get("citations"),
                "notes": grade.get("notes", ""),
            },
            "needs_grade": found.needs_grade,
            "carried_over": found.carried_over,
            "state": _STATES[state][0],
            "state_class": _STATES[state][1],
        }

    def cards(self) -> list[dict[str, Any]]:
        """Return every card; the ones that still need a grade come first."""
        grades = self.store.all()
        cards = [self.card(index, grades) for index in range(len(self.answers))]
        return sorted(cards, key=lambda card: not card["needs_grade"])


def create_grading_app(report_path: Path, store: GradeStore) -> FastAPI:
    """Return the grading app for the report at `report_path`."""
    grading = Grading(report_path, store)
    source = resources.files("librag.evaluation").joinpath("grading.html")
    environment = Environment(autoescape=select_autoescape(default=True))
    template = environment.from_string(source.read_text("utf-8"))
    app = FastAPI(title="LibRag answer grading", docs_url=None, redoc_url=None)

    @app.get("/")
    def page() -> HTMLResponse:
        """Show a card per answer, with its grade controls."""
        cards = grading.cards()
        return HTMLResponse(
            template.render(
                report=grading.name,
                grades_file=str(store.path),
                cards=cards,
                to_grade=sum(1 for card in cards if card["needs_grade"]),
                quality_grades=QUALITY_GRADES,
                citation_grades=CITATION_GRADES,
                citation_labels=CITATION_LABELS,
            )
        )

    @app.get("/app.css")
    def stylesheet() -> Response:
        """Return the app's stylesheet, for type and colour."""
        css = resources.files("librag").joinpath("static/app.css").read_text("utf-8")
        return Response(css, media_type="text/css")

    @app.get("/api/cards")
    def cards() -> dict[str, Any]:
        """List the cards, the ones that still need a grade first."""
        found = grading.cards()
        return {
            "report": grading.name,
            "to_grade": sum(1 for card in found if card["needs_grade"]),
            "cards": found,
        }

    @app.put("/api/answers/{index}/grade")
    async def grade(index: int, request: Request) -> JSONResponse:
        """Save a change to the grade of answer `index`, and return its card."""
        if not 0 <= index < len(grading.answers):
            return JSONResponse(
                {"error": "No answer with this number"},
                status_code=HTTPStatus.NOT_FOUND,
            )
        try:
            change = await request.json()
        except ValueError:
            change = None
        if not isinstance(change, dict):
            return JSONResponse(
                {"error": "The body must be a JSON object"},
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        try:
            store.save(grading.answers[index], grading.name, change)
        except GradeError as error:
            return JSONResponse(
                {"error": str(error)}, status_code=HTTPStatus.UNPROCESSABLE_ENTITY
            )
        grades = store.all()
        to_grade = sum(
            1
            for i in range(len(grading.answers))
            if grading.card(i, grades)["needs_grade"]
        )
        return JSONResponse({**grading.card(index, grades), "to_grade": to_grade})

    return app
