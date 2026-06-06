import json
from pathlib import Path

import pytest

from spyweb.audit import read_trace_events, write_trace
from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import QuestionAnswered, SecondAnswerBought, TraceStep
from spyweb.core.model import NothingAnswer, Question, Sense, SpyAnswer, SpyId


def test_writes_structured_trace_atomically(tmp_path: Path) -> None:
    event = QuestionAnswered(Question(SpyId(2), Sense.HEAR), NothingAnswer())
    trace = (TraceStep(1, event, 100, 40, 20, 12),)
    path = tmp_path / "game.json"

    write_trace(trace, path)

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["format"] == "spyweb-trace"
    assert record["steps"][0]["event"] == {
        "type": "question_answered",
        "question": {"spy": 2, "sense": "hear"},
        "answer": {"kind": "nothing"},
    }
    assert read_trace_events(path, FIXTURE_RULES) == (event,)


def test_reads_second_answer_and_rejects_unknown_format(tmp_path: Path) -> None:
    question = Question(SpyId(0), Sense.POINT)
    event = SecondAnswerBought(question, NothingAnswer(), SpyAnswer(SpyId(2)))
    path = tmp_path / "game.json"
    write_trace((TraceStep(1, event, 100, 20, 15, 5),), path)

    assert read_trace_events(path, FIXTURE_RULES) == (event,)

    path.write_text('{"format": "other", "version": 1, "steps": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Not a Spy Web trace"):
        read_trace_events(path, FIXTURE_RULES)
