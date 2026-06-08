from __future__ import annotations

from spyweb.core.model import QuestionId
from spyweb.solver.belief import Belief, QuestionScore, rank_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe

type Observation = tuple[int, ...]


def best_non_nothing_question(
    universe: Universe,
    encoding: Encoding,
    belief: Belief,
    observations: tuple[Observation, ...],
) -> QuestionScore:
    asked = {
        QuestionId(observation[1])
        for observation in observations
        if observation[0] == 0
    }
    ranked = rank_questions(universe, belief)
    candidates = tuple(score for score in ranked if score.question not in asked) or ranked
    return min(
        candidates,
        key=lambda score: (
            -sum(
                partition.boards
                for partition in score.partitions
                if partition.answer != encoding.nothing
            ),
            score.worst_pairs,
            score.worst_boards,
        ),
    )
