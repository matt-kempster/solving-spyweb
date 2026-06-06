from dataclasses import dataclass

from spyweb.core.model import (
    Answer,
    AnswerCode,
    LandmarkAnswer,
    LandmarkId,
    NothingAnswer,
    Question,
    QuestionId,
    Rules,
    Sense,
    SpyAnswer,
    SpyId,
)


@dataclass(frozen=True)
class Encoding:
    rules: Rules

    @property
    def question_count(self) -> int:
        return len(self.rules.spies) * len(Sense)

    @property
    def nothing(self) -> AnswerCode:
        return AnswerCode(len(self.rules.spies) + len(self.rules.landmarks))

    def question_id(self, question: Question) -> QuestionId:
        if not self.rules.spies[int(question.spy)].directions[question.sense]:
            spy = self.rules.spies[int(question.spy)]
            raise ValueError(f"{spy.name} cannot {question.sense.name.lower()}")
        return QuestionId(int(question.spy) * len(Sense) + int(question.sense))

    def decode_question(self, question: QuestionId) -> Question:
        return Question(SpyId(int(question) // len(Sense)), Sense(int(question) % len(Sense)))

    def question_available(self, question: QuestionId) -> bool:
        decoded = self.decode_question(question)
        return bool(self.rules.spies[int(decoded.spy)].directions[decoded.sense])

    def answer_code(self, answer: Answer) -> AnswerCode:
        if isinstance(answer, NothingAnswer):
            return self.nothing
        if isinstance(answer, SpyAnswer):
            return AnswerCode(answer.spy)
        return AnswerCode(len(self.rules.spies) + int(answer.landmark))

    def decode_answer(self, code: AnswerCode) -> Answer:
        if code == self.nothing:
            return NothingAnswer()
        if code < len(self.rules.spies):
            return SpyAnswer(SpyId(code))
        return LandmarkAnswer(LandmarkId(code - len(self.rules.spies)))
