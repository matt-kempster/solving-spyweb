from __future__ import annotations

import json
from pathlib import Path

from spyweb.core.events import (
    AccusationResolved,
    ObservedEvent,
    QuestionAnswered,
    SecondAnswerBought,
    Trace,
    TraceStep,
)
from spyweb.core.model import Answer, NothingAnswer, Question, SpyAnswer

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def _answer_record(answer: Answer) -> dict[str, JsonValue]:
    if isinstance(answer, NothingAnswer):
        return {"kind": "nothing"}
    if isinstance(answer, SpyAnswer):
        return {"kind": "spy", "spy": int(answer.spy)}
    return {"kind": "landmark", "landmark": int(answer.landmark)}


def _question_record(question: Question) -> dict[str, JsonValue]:
    return {"spy": int(question.spy), "sense": question.sense.name.lower()}


def _event_record(event: ObservedEvent) -> dict[str, JsonValue]:
    if isinstance(event, QuestionAnswered):
        return {
            "type": "question_answered",
            "question": _question_record(event.question),
            "answer": _answer_record(event.answer),
        }
    if isinstance(event, SecondAnswerBought):
        return {
            "type": "second_answer_bought",
            "question": _question_record(event.question),
            "first": _answer_record(event.first),
            "second": _answer_record(event.second),
            "cost": event.cost,
        }
    if isinstance(event, AccusationResolved):
        return {
            "type": "accusation_resolved",
            "ringleader": int(event.ringleader),
            "hideout": int(event.hideout),
            "correct": event.correct,
        }
    raise TypeError(f"Unsupported event: {type(event).__name__}")


def _step_record(step: TraceStep) -> dict[str, JsonValue]:
    return {
        "sequence": step.sequence,
        "event": _event_record(step.event),
        "boards_before": step.boards_before,
        "boards_after": step.boards_after,
        "pairs_before": step.pairs_before,
        "pairs_after": step.pairs_after,
    }


def write_trace(trace: Trace, path: Path) -> None:
    record: dict[str, JsonValue] = {
        "format": "spyweb-trace",
        "version": 1,
        "steps": [_step_record(step) for step in trace],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
