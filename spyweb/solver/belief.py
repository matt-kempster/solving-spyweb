from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from spyweb.core.model import AnswerCode, QuestionId
from spyweb.solver.universe import Universe

Belief = npt.NDArray[np.uint32]


def _belief(values: npt.NDArray[np.uint32]) -> Belief:
    return np.asarray(values, dtype=np.uint32)


@dataclass(frozen=True)
class Partition:
    answer: AnswerCode
    boards: int
    pairs: int


@dataclass(frozen=True)
class QuestionScore:
    question: QuestionId
    worst_boards: int
    worst_pairs: int
    partitions: tuple[Partition, ...]


def full_belief(universe: Universe) -> Belief:
    return np.arange(universe.board_count, dtype=np.uint32)


def pair_count(universe: Universe, belief: Belief) -> int:
    keys = universe.ringleader[belief] * universe.city_count + universe.hideout[belief]
    return int(np.unique(keys).size)


def filter_first_answer(
    universe: Universe, belief: Belief, question: QuestionId, observed: AnswerCode
) -> Belief:
    a0 = universe.answer0[int(question), belief]
    if universe.dual_question[int(question)]:
        a1 = universe.answer1[int(question), belief]
        return _belief(belief[(a0 == observed) | (a1 == observed)])
    return _belief(belief[a0 == observed])


def filter_paid_second(
    universe: Universe,
    belief: Belief,
    question: QuestionId,
    first: AnswerCode,
    second: AnswerCode,
) -> Belief:
    a0 = universe.answer0[int(question), belief]
    a1 = universe.answer1[int(question), belief]
    return _belief(belief[((a0 == first) & (a1 == second)) | ((a1 == first) & (a0 == second))])


def score_question(universe: Universe, belief: Belief, question: QuestionId) -> QuestionScore:
    answers = np.unique(
        np.concatenate(
            (universe.answer0[int(question), belief], universe.answer1[int(question), belief])
        )
    )
    partitions = []
    for answer in answers:
        code = AnswerCode(int(answer))
        bucket = filter_first_answer(universe, belief, question, code)
        partitions.append(Partition(code, int(bucket.size), pair_count(universe, bucket)))
    return QuestionScore(
        question,
        max(partition.boards for partition in partitions),
        max(partition.pairs for partition in partitions),
        tuple(partitions),
    )


def rank_questions(universe: Universe, belief: Belief) -> tuple[QuestionScore, ...]:
    return tuple(
        sorted(
            (
                score_question(universe, belief, QuestionId(q))
                for q in range(universe.answer0.shape[0])
            ),
            key=lambda score: (score.worst_pairs, score.worst_boards),
        )
    )
