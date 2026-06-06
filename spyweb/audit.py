from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from spyweb.core.events import (
    AccusationResolved,
    ObservedEvent,
    QuestionAnswered,
    SecondAnswerBought,
    Trace,
    TraceStep,
)
from spyweb.core.model import (
    Answer,
    CityId,
    LandmarkAnswer,
    LandmarkId,
    NothingAnswer,
    Question,
    Rules,
    Sense,
    SpyAnswer,
    SpyId,
)
from spyweb.core.rules import rules_fingerprint

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
TRACE_FORMAT_VERSION = 2


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


def write_trace(trace: Trace, path: Path, rules: Rules) -> None:
    record: dict[str, JsonValue] = {
        "format": "spyweb-trace",
        "version": TRACE_FORMAT_VERSION,
        "rules_fingerprint": rules_fingerprint(rules),
        "steps": [_step_record(step) for step in trace],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _record(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _integer(record: dict[str, JsonValue], key: str, context: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _boolean(record: dict[str, JsonValue], key: str, context: str) -> bool:
    value = record.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _question_from_record(value: JsonValue, rules: Rules) -> Question:
    record = _record(value, "question")
    spy = _integer(record, "spy", "question")
    if spy < 0 or spy >= len(rules.spies):
        raise ValueError(f"question.spy is out of range: {spy}")
    sense_name = record.get("sense")
    if not isinstance(sense_name, str):
        raise ValueError("question.sense must be a string")
    try:
        sense = Sense[sense_name.upper()]
    except KeyError as error:
        raise ValueError(f"Unknown question sense: {sense_name}") from error
    return Question(SpyId(spy), sense)


def _answer_from_record(value: JsonValue, rules: Rules) -> Answer:
    record = _record(value, "answer")
    kind = record.get("kind")
    if kind == "nothing":
        return NothingAnswer()
    if kind == "spy":
        spy = _integer(record, "spy", "answer")
        if spy < 0 or spy >= len(rules.spies):
            raise ValueError(f"answer.spy is out of range: {spy}")
        return SpyAnswer(SpyId(spy))
    if kind == "landmark":
        landmark = _integer(record, "landmark", "answer")
        if landmark < 0 or landmark >= len(rules.landmarks):
            raise ValueError(f"answer.landmark is out of range: {landmark}")
        return LandmarkAnswer(LandmarkId(landmark))
    raise ValueError(f"Unknown answer kind: {kind}")


def _event_from_record(value: JsonValue, rules: Rules) -> ObservedEvent:
    record = _record(value, "event")
    event_type = record.get("type")
    if event_type == "question_answered":
        return QuestionAnswered(
            _question_from_record(record.get("question"), rules),
            _answer_from_record(record.get("answer"), rules),
        )
    if event_type == "second_answer_bought":
        return SecondAnswerBought(
            _question_from_record(record.get("question"), rules),
            _answer_from_record(record.get("first"), rules),
            _answer_from_record(record.get("second"), rules),
            _integer(record, "cost", "event"),
        )
    if event_type == "accusation_resolved":
        ringleader = _integer(record, "ringleader", "event")
        hideout = _integer(record, "hideout", "event")
        if ringleader < 0 or ringleader >= len(rules.spies):
            raise ValueError(f"event.ringleader is out of range: {ringleader}")
        if hideout < 0 or hideout >= len(rules.cities):
            raise ValueError(f"event.hideout is out of range: {hideout}")
        return AccusationResolved(
            SpyId(ringleader),
            CityId(hideout),
            _boolean(record, "correct", "event"),
        )
    raise ValueError(f"Unknown event type: {event_type}")


def read_trace_events(path: Path, rules: Rules) -> tuple[ObservedEvent, ...]:
    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    record = _record(value, "trace")
    if record.get("format") != "spyweb-trace":
        raise ValueError("Not a Spy Web trace")
    if record.get("version") != TRACE_FORMAT_VERSION:
        raise ValueError(f"Unsupported trace version: {record.get('version')}")
    if record.get("rules_fingerprint") != rules_fingerprint(rules):
        raise ValueError("Trace was recorded against different rules")
    steps = record.get("steps")
    if not isinstance(steps, list):
        raise ValueError("trace.steps must be an array")
    return tuple(
        _event_from_record(_record(step, f"trace.steps[{index}]").get("event"), rules)
        for index, step in enumerate(steps)
    )
