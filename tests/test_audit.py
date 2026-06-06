import json
from pathlib import Path

from spyweb.audit import write_trace
from spyweb.core.events import QuestionAnswered, TraceStep
from spyweb.core.model import NothingAnswer, Question, Sense, SpyId


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
