from pathlib import Path

import numpy as np
import pytest

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import QuestionAnswered
from spyweb.core.model import LandmarkAnswer, Question, QuestionId, Sense, SpyId
from spyweb.core.rules import answer_question, rules_fingerprint, validate_board
from spyweb.solver.belief import (
    full_belief,
    pair_candidates,
    pair_count,
    rank_questions,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.hybrid_policy import (
    exact_endgame_action,
    recommend_hybrid_questions,
    recommend_prior_questions,
)
from spyweb.solver.policy import recommend_questions
from spyweb.solver.replay import ReplayState, apply_event
from spyweb.solver.universe import Universe, build_universe


def test_scores_replays_and_round_trips_cache(tmp_path: Path) -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 2_000)
    belief = full_belief(universe)
    assert pair_count(universe, belief) == 81
    assert len(pair_candidates(universe, belief)) == 81
    ranking = rank_questions(universe, belief)
    assert len(ranking) == 19
    assert all(universe.available_question[int(score.question)] for score in ranking)
    with pytest.raises(ValueError, match="Raven cannot hear"):
        encoding.question_id(Question(SpyId(0), Sense.HEAR))

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
            if not universe.available_question[q]:
                continue
            question = encoding.decode_question(QuestionId(q))
            answers = answer_question(FIXTURE_RULES, board, question)
            assert universe.answer0[q, board_index] == encoding.answer_code(answers[0])
            assert universe.answer1[q, board_index] == encoding.answer_code(answers[-1])


def test_policy_uses_bounded_lookahead_and_reports_fallback() -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 500)
    belief = full_belief(universe)

    fallback = recommend_questions(universe, belief, depth=2, max_lookahead_boards=100)
    assert fallback.requested_depth == 2
    assert fallback.effective_depth == 1

    narrowed = belief[:100]
    deeper = recommend_questions(universe, narrowed, depth=2, max_lookahead_boards=100)
    assert deeper.effective_depth == 2
    assert deeper.best.worst_leaf_pairs <= deeper.best.immediate.worst_pairs


def test_policy_limits_only_recursive_question_candidates() -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 500)
    belief = full_belief(universe)

    result = recommend_questions(
        universe,
        belief,
        depth=2,
        max_lookahead_boards=500,
        branching_limit=2,
    )

    assert result.effective_depth == 2
    assert len(result.scores) == int(universe.available_question.sum())


def test_hybrid_policy_uses_component_shortlist_and_exact_endgame() -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 500)
    belief = full_belief(universe)

    hybrid = recommend_hybrid_questions(
        universe,
        encoding,
        belief,
        (),
        depth=1,
        max_lookahead_boards=500,
        branching_limit=5,
    )

    assert len(hybrid.scores) == 8

    pair_keys = universe.ringleader * universe.city_count + universe.hideout
    endgame = np.asarray(
        [int(np.flatnonzero(pair_keys == key)[0]) for key in np.unique(pair_keys)[:3]],
        dtype=np.uint32,
    )
    exact = exact_endgame_action(universe, endgame)

    assert exact.actions <= 3
    assert (exact.question is None) != (exact.accusation is None)


def test_prior_policy_searches_a_bounded_diverse_shortlist() -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 500)
    belief = full_belief(universe)

    prior = recommend_prior_questions(
        universe,
        encoding,
        belief,
        (),
        depth=2,
        max_lookahead_boards=500,
        branching_limit=8,
    )

    assert prior.effective_depth == 2
    assert 3 <= len(prior.scores) <= 8
