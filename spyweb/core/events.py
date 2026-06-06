from __future__ import annotations

from dataclasses import dataclass

from spyweb.core.model import Answer, CityId, Question, SpyId


@dataclass(frozen=True)
class QuestionAnswered:
    question: Question
    answer: Answer


@dataclass(frozen=True)
class SecondAnswerBought:
    question: Question
    first: Answer
    second: Answer
    cost: int = 100_000


@dataclass(frozen=True)
class AccusationResolved:
    ringleader: SpyId
    hideout: CityId
    correct: bool


ObservedEvent = QuestionAnswered | SecondAnswerBought | AccusationResolved


@dataclass(frozen=True)
class TraceStep:
    sequence: int
    event: ObservedEvent
    boards_before: int
    boards_after: int
    pairs_before: int
    pairs_after: int


Trace = tuple[TraceStep, ...]
