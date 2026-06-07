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
    return int(np.count_nonzero(np.bincount(keys, minlength=universe.city_count**2)))


def pair_candidates(universe: Universe, belief: Belief) -> tuple[PairCandidate, ...]:
    keys = universe.ringleader[belief] * universe.city_count + universe.hideout[belief]
    counts = np.bincount(keys, minlength=universe.city_count**2)
    return tuple(
        PairCandidate(
            int(key) // universe.city_count,
            int(key) % universe.city_count,
            int(count),
        )
        for key, count in enumerate(counts)
        if count
    )


def _score_normal_question(
    universe: Universe, belief: Belief, question: QuestionId
) -> QuestionScore:
    pair_total = universe.city_count**2
    answers = universe.answer0[int(question), belief]
    answer_count = int(np.max(answers)) + 1
    pair_keys = universe.ringleader[belief] * universe.city_count + universe.hideout[belief]
    boards_by_answer = np.bincount(answers, minlength=answer_count)
    joint_keys = answers.astype(np.uint16) * pair_total + pair_keys.astype(np.uint16)
    pairs_by_answer = np.count_nonzero(
        np.bincount(joint_keys, minlength=answer_count * pair_total).reshape(
            answer_count, pair_total
        ),
        axis=1,
    )
    partitions = tuple(
        Partition(AnswerCode(int(answer)), int(boards), int(pairs_by_answer[answer]))
        for answer, boards in enumerate(boards_by_answer)
        if boards
    )
    return QuestionScore(
        question,
        max(partition.boards for partition in partitions),
        max(partition.pairs for partition in partitions),
        partitions,
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
    if not universe.dual_question[int(question)]:
        return _score_normal_question(universe, belief, question)
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
