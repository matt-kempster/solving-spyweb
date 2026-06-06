from pathlib import Path

import pytest

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import QuestionAnswered
from spyweb.core.model import LandmarkAnswer, Question, QuestionId, Sense, SpyId
from spyweb.core.rules import answer_question, validate_board
from spyweb.solver.belief import (
    full_belief,
    pair_candidates,
    pair_count,
    rank_questions,
    score_dual_payment,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.replay import ReplayState, apply_event
from spyweb.solver.universe import Universe, build_universe, rules_fingerprint


def test_scores_replays_and_round_trips_cache(tmp_path: Path) -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 2_000)
    belief = full_belief(universe)
    assert pair_count(universe, belief) == 81
    assert len(pair_candidates(universe, belief)) == 81
    assert len(rank_questions(universe, belief)) == 27
    dual = score_dual_payment(
        universe, belief, encoding.question_id(Question(SpyId(0), Sense.POINT))
    )
    assert dual
    assert all(option.paid_worst_boards <= option.no_pay_boards for option in dual)

    event = QuestionAnswered(
        Question(SpyId(0), Sense.LOOK), LandmarkAnswer(FIXTURE_RULES.landmarks[0].id)
    )
    state = apply_event(universe, encoding, ReplayState(belief), event)
    assert state.belief.size < belief.size
    assert state.trace[0].boards_after == state.belief.size

    cache = tmp_path / "universe.npz"
    universe.save(cache)
    loaded = Universe.load(
        cache,
        expected_rules_fingerprint=rules_fingerprint(FIXTURE_RULES),
        expected_board_count=universe.board_count,
    )
    assert loaded.board_count == universe.board_count
    assert (loaded.answer0 == universe.answer0).all()
    with pytest.raises(ValueError, match="expected 2,001"):
        Universe.load(cache, expected_board_count=2_001)


def test_numpy_answers_match_pure_rules_engine() -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 500)

    for board_index in range(0, universe.board_count, 17):
        board = universe.board(board_index)
        validate_board(FIXTURE_RULES, board)
        for q in range(encoding.question_count):
            question = encoding.decode_question(QuestionId(q))
            answers = answer_question(FIXTURE_RULES, board, question)
            assert universe.answer0[q, board_index] == encoding.answer_code(answers[0])
            assert universe.answer1[q, board_index] == encoding.answer_code(answers[-1])
