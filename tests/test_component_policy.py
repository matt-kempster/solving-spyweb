import numpy as np

from spyweb.core.catalog import BIRD_RULES
from spyweb.core.model import Faction, QuestionId
from spyweb.solver.belief import full_belief
from spyweb.solver.component_policy import rank_component_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe


def _component_policy_fixture() -> tuple[Universe, Encoding]:
    encoding = Encoding(BIRD_RULES)
    answers = np.full((encoding.question_count, 4), encoding.nothing, dtype=np.uint8)
    answers[0] = np.asarray([1, 1, encoding.nothing, encoding.nothing], dtype=np.uint8)
    answers[3] = np.asarray([2, 2, encoding.nothing, encoding.nothing], dtype=np.uint8)
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    available[3] = 1
    return (
        Universe(
            "test",
            np.asarray([0, 0, 1, 1], dtype=np.uint8),
            np.asarray([0, 1, 0, 1], dtype=np.uint8),
            np.zeros((4, len(BIRD_RULES.cities)), dtype=np.uint8),
            answers,
            answers,
            np.zeros(encoding.question_count, dtype=np.uint8),
            available,
        ),
        encoding,
    )


def test_component_policy_prefers_spy_edge_over_nothing() -> None:
    universe, encoding = _component_policy_fixture()

    ranked = rank_component_questions(universe, encoding, full_belief(universe), ())

    assert ranked[0].immediate.question == QuestionId(0)
    assert ranked[0].expected_structure_gain > 0
    assert ranked[0].spy_answer_boards == 2


def test_component_policy_skips_previously_asked_question() -> None:
    universe, encoding = _component_policy_fixture()

    ranked = rank_component_questions(
        universe,
        encoding,
        full_belief(universe),
        ((0, 0, 1),),
    )

    assert ranked[0].immediate.question == QuestionId(3)
    spy = BIRD_RULES.spies[int(encoding.decode_question(ranked[0].immediate.question).spy)]
    assert spy.faction is Faction.BIRD
