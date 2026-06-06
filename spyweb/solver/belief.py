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


@dataclass(frozen=True)
class PairCandidate:
    ringleader: int
    hideout: int
    boards: int


@dataclass(frozen=True)
class PaidSecondPartition:
    second: AnswerCode
    boards: int
    pairs: int


@dataclass(frozen=True)
class DualFirstOption:
    first: AnswerCode
    no_pay_boards: int
    no_pay_pairs: int
    paid_worst_boards: int
    paid_worst_pairs: int
    paid_partitions: tuple[PaidSecondPartition, ...]


def full_belief(universe: Universe) -> Belief:
    return np.arange(universe.board_count, dtype=np.uint32)


def pair_count(universe: Universe, belief: Belief) -> int:
    keys = universe.ringleader[belief] * universe.city_count + universe.hideout[belief]
    return int(np.unique(keys).size)


def pair_candidates(universe: Universe, belief: Belief) -> tuple[PairCandidate, ...]:
    keys = universe.ringleader[belief] * universe.city_count + universe.hideout[belief]
    unique, counts = np.unique(keys, return_counts=True)
    return tuple(
        PairCandidate(
            int(key) // universe.city_count,
            int(key) % universe.city_count,
            int(count),
        )
        for key, count in zip(unique, counts, strict=True)
    )


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


def score_dual_payment(
    universe: Universe, belief: Belief, question: QuestionId
) -> tuple[DualFirstOption, ...]:
    if not universe.dual_question[int(question)]:
        raise ValueError(f"Question {question} does not have two directions")
    answers = np.unique(
        np.concatenate(
            (universe.answer0[int(question), belief], universe.answer1[int(question), belief])
        )
    )
    options = []
    for answer in answers:
        first = AnswerCode(int(answer))
        first_bucket = filter_first_answer(universe, belief, question, first)
        a0 = universe.answer0[int(question), first_bucket]
        a1 = universe.answer1[int(question), first_bucket]
        other = np.where(a0 == first, a1, a0)
        paid_partitions = tuple(
            PaidSecondPartition(
                AnswerCode(int(second)),
                int((second_bucket := first_bucket[other == second]).size),
                pair_count(universe, _belief(second_bucket)),
            )
            for second in np.unique(other)
        )
        options.append(
            DualFirstOption(
                first,
                int(first_bucket.size),
                pair_count(universe, first_bucket),
                max(partition.boards for partition in paid_partitions),
                max(partition.pairs for partition in paid_partitions),
                paid_partitions,
            )
        )
    return tuple(options)


def rank_questions(universe: Universe, belief: Belief) -> tuple[QuestionScore, ...]:
    return tuple(
        sorted(
            (
                score_question(universe, belief, QuestionId(q))
                for q in range(universe.answer0.shape[0])
                if universe.available_question[q]
            ),
            key=lambda score: (score.worst_pairs, score.worst_boards),
        )
    )
