from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from spyweb.core.model import AnswerCode, QuestionId
from spyweb.solver.belief import (
    Belief,
    QuestionScore,
    filter_first_answer,
    rank_questions,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe

type Observation = tuple[int, ...]


@dataclass(frozen=True)
class ComponentQuestionScore:
    immediate: QuestionScore
    worst_remaining_ringleaders: int
    expected_remaining_ringleaders: int
    expected_structure_gain: int
    spy_answer_boards: int
    non_nothing_boards: int
    source_component_size: int


class _Components:
    def __init__(self, spy_count: int) -> None:
        self.parent = list(range(spy_count))
        self.size = [1] * spy_count
        self.anchored: set[int] = set()

    def root(self, spy: int) -> int:
        parent = self.parent[spy]
        if parent != spy:
            self.parent[spy] = self.root(parent)
        return self.parent[spy]

    def union(self, left: int, right: int) -> None:
        left_root = self.root(left)
        right_root = self.root(right)
        if left_root == right_root:
            return
        if self.size[left_root] < self.size[right_root]:
            left_root, right_root = right_root, left_root
        anchored = left_root in self.anchored or right_root in self.anchored
        self.parent[right_root] = left_root
        self.size[left_root] += self.size[right_root]
        self.anchored.discard(right_root)
        if anchored:
            self.anchored.add(left_root)

    def anchor(self, spy: int) -> None:
        self.anchored.add(self.root(spy))

    def component_size(self, spy: int) -> int:
        return self.size[self.root(spy)]

    def structure_gain(
        self, source: int, answer: AnswerCode, spy_count: int, nothing: AnswerCode
    ) -> int:
        source_root = self.root(source)
        if answer < spy_count:
            target_root = self.root(int(answer))
            return 0 if source_root == target_root else self.size[target_root]
        if answer == nothing:
            return 0
        return 0 if source_root in self.anchored else self.size[source_root]


def _component_state(
    encoding: Encoding, observations: tuple[Observation, ...]
) -> tuple[_Components, set[QuestionId]]:
    spy_count = len(encoding.rules.spies)
    components = _Components(spy_count)
    asked: set[QuestionId] = set()
    for observation in observations:
        kind = observation[0]
        if kind not in (0, 1):
            continue
        question = QuestionId(observation[1])
        source = int(encoding.decode_question(question).spy)
        answer = AnswerCode(observation[2] if kind == 0 else observation[3])
        if kind == 0:
            asked.add(question)
        if answer < spy_count:
            components.union(source, int(answer))
        elif answer < int(encoding.nothing):
            components.anchor(source)
    return components, asked


def rank_component_questions(
    universe: Universe,
    encoding: Encoding,
    belief: Belief,
    observations: tuple[Observation, ...],
) -> tuple[ComponentQuestionScore, ...]:
    components, asked = _component_state(encoding, observations)
    immediate_scores = rank_questions(universe, belief)
    unasked = tuple(score for score in immediate_scores if score.question not in asked)
    candidates = unasked or immediate_scores
    spy_count = len(encoding.rules.spies)
    nothing = encoding.nothing
    scores = []
    for immediate in candidates:
        source = int(encoding.decode_question(immediate.question).spy)
        ringleaders_by_partition = tuple(
            int(
                np.unique(
                    universe.ringleader[
                        filter_first_answer(
                            universe,
                            belief,
                            immediate.question,
                            partition.answer,
                        )
                    ]
                ).size
            )
            for partition in immediate.partitions
        )
        scores.append(
            ComponentQuestionScore(
                immediate,
                max(ringleaders_by_partition),
                sum(
                    partition.boards * ringleaders
                    for partition, ringleaders in zip(
                        immediate.partitions, ringleaders_by_partition, strict=True
                    )
                ),
                sum(
                    partition.boards
                    * components.structure_gain(source, partition.answer, spy_count, nothing)
                    for partition in immediate.partitions
                ),
                sum(
                    partition.boards
                    for partition in immediate.partitions
                    if partition.answer < spy_count
                ),
                sum(
                    partition.boards
                    for partition in immediate.partitions
                    if partition.answer != nothing
                ),
                components.component_size(source),
            )
        )
    return tuple(
        sorted(
            scores,
            key=lambda score: (
                score.worst_remaining_ringleaders,
                score.expected_remaining_ringleaders,
                -score.expected_structure_gain,
                -score.spy_answer_boards,
                -score.non_nothing_boards,
                -score.source_component_size,
                score.immediate.worst_pairs,
                score.immediate.worst_boards,
            ),
        )
    )
