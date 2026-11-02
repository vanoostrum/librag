# Copyright (C) 2026 Theo van Oostrum
"""Grades: Theo's judgement of each answer, kept in `eval-reports/grades.json`.

A grade is keyed by question, model and answer hash, so a later run's answer
that reads the same and cites the same passages finds it and keeps it.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

QUALITY_GRADES = (1, 2, 3, 4, 5)
CITATION_GRADES = ("correct", "partly", "wrong")
CITATION_LABELS = {"correct": "Correct", "partly": "Partly correct", "wrong": "Wrong"}


class GradeError(ValueError):
    """A grade is not valid. The message says which field and why."""


def grade_key(answer: Mapping[str, Any]) -> str:
    """Return the key of `answer`'s grade: question, model and answer hash."""
    return f"{answer['question_id']}|{answer['model']}|{answer['answer_hash']}"


def is_complete(grade: Mapping[str, Any] | None) -> bool:
    """Return whether `grade` has both a quality and a citation grade."""
    if grade is None:
        return False
    return grade.get("quality") is not None and grade.get("citations") is not None


def check_change(change: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fields of a grade change, or raise `GradeError`.

    A change holds any of `quality` (1 to 5, or None to clear), `citations`
    (correct, partly or wrong, or None to clear) and `notes` (text).
    """
    unknown = sorted(set(change) - {"quality", "citations", "notes"})
    if unknown:
        msg = f"{unknown[0]}: not a grade field"
        raise GradeError(msg)
    checked: dict[str, Any] = {}
    if "quality" in change:
        quality = change["quality"]
        if quality is not None and (
            isinstance(quality, bool) or quality not in QUALITY_GRADES
        ):
            msg = "quality: must be a whole number from 1 to 5"
            raise GradeError(msg)
        checked["quality"] = quality
    if "citations" in change:
        citations = change["citations"]
        if citations is not None and citations not in CITATION_GRADES:
            msg = "citations: must be correct, partly or wrong"
            raise GradeError(msg)
        checked["citations"] = citations
    if "notes" in change:
        if not isinstance(change["notes"], str):
            msg = "notes: must be text"
            raise GradeError(msg)
        checked["notes"] = change["notes"]
    return checked


@dataclass(frozen=True)
class Graded:
    """An answer's grade as a report shows it, and whether it was carried over."""

    grade: Mapping[str, Any] | None
    carried_over: bool

    @property
    def needs_grade(self) -> bool:
        """Whether the answer still needs a quality or a citation grade."""
        return not is_complete(self.grade)


def graded(
    grades: Mapping[str, Mapping[str, Any]], answer: Mapping[str, Any], report: str
) -> Graded:
    """Return `answer`'s grade in `report`.

    A complete grade that was given on another report is carried over: the
    answer reads the same and cites the same passages, so it needs no new grade.
    """
    grade = grades.get(grade_key(answer))
    carried = grade is not None and grade.get("report") != report and is_complete(grade)
    return Graded(grade, carried_over=carried)


class GradeStore:
    """The grades in a JSON file, read on each call and written on each change."""

    def __init__(self, path: Path) -> None:
        """Keep the grades in the file at `path`, made on the first grade."""
        self.path = path

    def all(self) -> dict[str, dict[str, Any]]:
        """Return every grade, by key."""
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return dict(data.get("grades", {}))

    def save(
        self,
        answer: Mapping[str, Any],
        report: str,
        change: Mapping[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Apply `change` to `answer`'s grade, write the file, and return the grade."""
        checked = check_change(change)
        grades = self.all()
        key = grade_key(answer)
        grade = {
            "question_id": answer["question_id"],
            "model": answer["model"],
            "answer_hash": answer["answer_hash"],
            "quality": None,
            "citations": None,
            "notes": "",
            **grades.get(key, {}),
            **checked,
            "report": report,
            "updated_at": (now or datetime.now(UTC)).isoformat(),
        }
        grades[key] = grade
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(".part")
        partial.write_text(
            json.dumps({"grades": grades}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        partial.replace(self.path)
        return grade


def latest_report(reports_dir: Path) -> Path | None:
    """Return the newest `answers-<timestamp>.json` in `reports_dir`, if any."""
    reports: Sequence[Path] = sorted(reports_dir.glob("answers-*.json"))
    return reports[-1] if reports else None
