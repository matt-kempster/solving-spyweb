import numpy as np

from spyweb.core.catalog import BIRD_RULES
from spyweb.core.model import QuestionId
from spyweb.solver.belief import full_belief
from spyweb.solver.encoding import Encoding
from spyweb.solver.human_policy import HumanPhase, rank_human_questions
from spyweb.solver.universe import Universe


def _human_policy_fixture(*, available: tuple[int, ...]) -> tuple[Universe, Encoding]:
    encoding = Encoding(BIRD_RULES)
    answers = np.full((encoding.question_count, 4), encoding.nothing, dtype=np.uint8)
    available_questions = np.zeros(encoding.question_count, dtype=np.uint8)
    for question in available:
        available_questions[question] = 1
    return (
        Universe(
            "test",
            np.asarray([0, 0, 1, 1], dtype=np.uint8),
            np.asarray([0, 1, 0, 1], dtype=np.uint8),
            np.zeros((4, len(BIRD_RULES.cities)), dtype=np.uint8),
            answers,
            answers,
            np.zeros(encoding.question_count, dtype=np.uint8),
            available_questions,
        ),
        encoding,
    )


def test_human_policy_moves_off_a_nothing_source_while_exploring() -> None:
    universe, encoding = _human_policy_fixture(available=(1, 3))
    universe.answer0[1] = np.asarray([1, 1, encoding.nothing, encoding.nothing], dtype=np.uint8)
    universe.answer1[1] = universe.answer0[1]
    universe.answer0[3] = np.asarray([2, 2, encoding.nothing, encoding.nothing], dtype=np.uint8)
    universe.answer1[3] = universe.answer0[3]

    ranked = rank_human_questions(
        universe,
        encoding,
        full_belief(universe),
        ((0, 0, int(encoding.nothing)),),
    )

    assert ranked[0].phase is HumanPhase.EXPLORE
    assert ranked[0].immediate.question == QuestionId(3)


def test_human_policy_expands_the_focus_component_before_starting_a_new_edge() -> None:
    universe, encoding = _human_policy_fixture(available=(2, 9))
    universe.answer0[2] = np.asarray([1, 1, encoding.nothing, encoding.nothing], dtype=np.uint8)
    universe.answer1[2] = universe.answer0[2]
    universe.answer0[9] = np.asarray([2, 2, encoding.nothing, encoding.nothing], dtype=np.uint8)
    universe.answer1[9] = universe.answer0[9]

    ranked = rank_human_questions(
        universe,
        encoding,
        full_belief(universe),
        ((0, 0, 5),),
    )

    assert ranked[0].phase is HumanPhase.BUILD
    assert ranked[0].immediate.question == QuestionId(2)
    assert ranked[0].source_in_focus_component
