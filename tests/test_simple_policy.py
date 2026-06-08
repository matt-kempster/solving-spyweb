import numpy as np

from spyweb.core.catalog import BIRD_RULES
from spyweb.core.model import QuestionId
from spyweb.solver.belief import full_belief
from spyweb.solver.encoding import Encoding
from spyweb.solver.simple_policy import best_non_nothing_question
from spyweb.solver.universe import Universe


def test_non_nothing_policy_prefers_likely_answer_and_avoids_repeats() -> None:
    encoding = Encoding(BIRD_RULES)
    answers = np.full((encoding.question_count, 4), encoding.nothing, dtype=np.uint8)
    answers[0] = np.asarray([1, 1, 1, encoding.nothing], dtype=np.uint8)
    answers[3] = np.asarray([2, 2, encoding.nothing, encoding.nothing], dtype=np.uint8)
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    available[3] = 1
    universe = Universe(
        "test",
        np.asarray([0, 0, 1, 1], dtype=np.uint8),
        np.asarray([0, 1, 0, 1], dtype=np.uint8),
        np.zeros((4, len(BIRD_RULES.cities)), dtype=np.uint8),
        answers,
        answers,
        np.zeros(encoding.question_count, dtype=np.uint8),
        available,
    )

    first = best_non_nothing_question(universe, encoding, full_belief(universe), ())
    second = best_non_nothing_question(
        universe,
        encoding,
        full_belief(universe),
        ((0, 0, 1),),
    )

    assert first.question == QuestionId(0)
    assert second.question == QuestionId(3)
