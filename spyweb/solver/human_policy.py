from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from spyweb.core.model import AnswerCode, QuestionId
from spyweb.solver.belief import (
    Belief,
    QuestionScore,
    filter_first_answer,
    rank_questions,
)
from spyweb.solver.component_policy import Observation
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe


class HumanPhase(StrEnum):
    EXPLORE = "explore"
    BUILD = "build"
    LEADER_HUNT = "leader_hunt"


@dataclass(frozen=True)
class HumanQuestionScore:
    immediate: QuestionScore
    phase: HumanPhase
    source_component_size: int
    source_in_focus_component: bool
    source_nothing_count: int
    remaining_source_questions: int
    worst_remaining_ringleaders: int
    worst_remaining_hideouts: int
    expected_remaining_ringleaders: float
    expected_remaining_hideouts: float
    expected_structure_gain: float
    source_ringleader_probability: float
    landmark_probability: float
    spy_answer_probability: float
    non_nothing_probability: float


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

    def focus_roots(self) -> set[int]:
        useful = {
            self.root(spy)
            for spy in range(len(self.parent))
            if self.component_size(spy) > 1 or self.root(spy) in self.anchored
        }
        if not useful:
            return set()
        largest = max(self.size[root] for root in useful)
        anchored_largest = {
            root for root in useful if self.size[root] == largest and root in self.anchored
        }
        return anchored_largest or {root for root in useful if self.size[root] == largest}

    def structure_gain(
        self, source: int, answer: AnswerCode, spy_count: int, nothing: AnswerCode
    ) -> int:
        source_root = self.root(source)
        if answer < spy_count:
            target_root = self.root(int(answer))
            if source_root == target_root:
                return 0
            # Growing an existing component is more useful than starting an isolated edge.
            return self.size[source_root] * self.size[target_root]
        if answer == nothing or source_root in self.anchored:
            return 0
        return self.size[source_root]


@dataclass(frozen=True)
class _HumanState:
    components: _Components
    asked: frozenset[QuestionId]
    nothing_by_spy: tuple[int, ...]


def _human_state(encoding: Encoding, observations: tuple[Observation, ...]) -> _HumanState:
    spy_count = len(encoding.rules.spies)
    components = _Components(spy_count)
    asked: set[QuestionId] = set()
    nothing_by_spy = [0] * spy_count
    for observation in observations:
        if observation[0] not in (0, 1):
            continue
        question = QuestionId(observation[1])
        source = int(encoding.decode_question(question).spy)
        answer = AnswerCode(observation[2] if observation[0] == 0 else observation[3])
        if observation[0] == 0:
            asked.add(question)
        if answer < spy_count:
            components.union(source, int(answer))
        elif answer < int(encoding.nothing):
            components.anchor(source)
        else:
            nothing_by_spy[source] += 1
    return _HumanState(components, frozenset(asked), tuple(nothing_by_spy))


def _distinct(values: np.ndarray) -> int:
    return int(np.unique(values).size)


def _question_score(
    universe: Universe,
    encoding: Encoding,
    belief: Belief,
    immediate: QuestionScore,
    state: _HumanState,
    phase: HumanPhase,
) -> HumanQuestionScore:
    spy_count = len(encoding.rules.spies)
    source = int(encoding.decode_question(immediate.question).spy)
    branches = tuple(
        (
            partition,
            filter_first_answer(universe, belief, immediate.question, partition.answer),
        )
        for partition in immediate.partitions
    )
    branch_weight = sum(int(branch.size) for _, branch in branches)
    expected_ringleaders = sum(
        int(branch.size) * _distinct(universe.ringleader[branch]) for _, branch in branches
    ) / branch_weight
    expected_hideouts = sum(
        int(branch.size) * _distinct(universe.hideout[branch]) for _, branch in branches
    ) / branch_weight
    expected_structure_gain = sum(
        int(branch.size)
        * state.components.structure_gain(source, partition.answer, spy_count, encoding.nothing)
        for partition, branch in branches
    ) / branch_weight
    answers = universe.answer0[int(immediate.question), belief]
    if universe.dual_question[int(immediate.question)]:
        answers = np.concatenate((answers, universe.answer1[int(immediate.question), belief]))
    answer_total = int(answers.size)
    source_questions = {
        QuestionId(q)
        for q in range(universe.answer0.shape[0])
        if universe.available_question[q]
        and int(encoding.decode_question(QuestionId(q)).spy) == source
    }
    focus_roots = state.components.focus_roots()
    return HumanQuestionScore(
        immediate,
        phase,
        state.components.component_size(source),
        state.components.root(source) in focus_roots,
        state.nothing_by_spy[source],
        len(source_questions - state.asked),
        max(_distinct(universe.ringleader[branch]) for _, branch in branches),
        max(_distinct(universe.hideout[branch]) for _, branch in branches),
        expected_ringleaders,
        expected_hideouts,
        expected_structure_gain,
        float(np.count_nonzero(universe.ringleader[belief] == source)) / int(belief.size),
        float(np.count_nonzero((answers >= spy_count) & (answers < int(encoding.nothing))))
        / answer_total,
        float(np.count_nonzero(answers < spy_count)) / answer_total,
        float(np.count_nonzero(answers != encoding.nothing)) / answer_total,
    )


def rank_human_questions(
    universe: Universe,
    encoding: Encoding,
    belief: Belief,
    observations: tuple[Observation, ...],
) -> tuple[HumanQuestionScore, ...]:
    state = _human_state(encoding, observations)
    immediate_scores = rank_questions(universe, belief)
    unasked = tuple(score for score in immediate_scores if score.question not in state.asked)
    candidates = unasked or immediate_scores
    informative = tuple(score for score in candidates if score.worst_boards < int(belief.size))
    candidates = informative or candidates
    hideouts = _distinct(universe.hideout[belief])
    focus_exists = bool(state.components.focus_roots())
    phase = (
        HumanPhase.LEADER_HUNT
        if hideouts == 1
        else HumanPhase.BUILD
        if focus_exists
        else HumanPhase.EXPLORE
    )
    scores = tuple(
        _question_score(universe, encoding, belief, immediate, state, phase)
        for immediate in candidates
    )

    def key(score: HumanQuestionScore) -> tuple[float | int, ...]:
        common = (
            score.immediate.worst_pairs,
            score.immediate.worst_boards,
        )
        if phase is HumanPhase.LEADER_HUNT:
            return (
                score.worst_remaining_ringleaders,
                score.expected_remaining_ringleaders,
                -score.source_ringleader_probability,
                -score.non_nothing_probability,
                *common,
            )
        if phase is HumanPhase.BUILD:
            return (
                not score.source_in_focus_component,
                score.worst_remaining_hideouts,
                score.expected_remaining_hideouts,
                -score.expected_structure_gain,
                score.source_nothing_count,
                -score.non_nothing_probability,
                *common,
            )
        return (
            score.source_nothing_count > 0,
            -score.remaining_source_questions,
            -score.landmark_probability,
            -score.spy_answer_probability,
            score.worst_remaining_hideouts,
            score.worst_remaining_ringleaders,
            *common,
        )

    return tuple(sorted(scores, key=key))
