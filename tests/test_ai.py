from dataclasses import replace
from pathlib import Path
from random import Random

import numpy as np

from spyweb.ai import (
    AiKnowledge,
    ai_search_depth,
    choose_defensive_board,
    load_ai_knowledge,
    observe_accusation,
    recommended_action,
    should_buy_extra_for_accusation,
    should_buy_tempo_extra,
)
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import CAMPAIGN_TARGET, GameState, TurnPhase, new_game
from spyweb.core.model import Question
from spyweb.core.rules import rules_fingerprint, validate_board
from spyweb.solver.belief import PairCandidate, full_belief, pair_candidates
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe, build_universe


def _knowledge_with_one_pair() -> AiKnowledge:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    belief = full_belief(universe)
    first = belief[0]
    same_pair = belief[
        (universe.ringleader[belief] == universe.ringleader[first])
        & (universe.hideout[belief] == universe.hideout[first])
    ]
    return AiKnowledge(universe, encoding, same_pair)


def _ai_post_action_state(ai_money: int, opponent_money: int) -> GameState:
    state = new_game("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4)
    players = (
        replace(state.players[0], money=opponent_money),
        replace(state.players[1], money=ai_money),
    )
    return replace(state, players=players, turn=1, phase=TurnPhase.POST_ACTION)


def test_ai_search_depth_increases_as_belief_shrinks() -> None:
    assert ai_search_depth(250_001) == 1
    assert ai_search_depth(250_000) == 2
    assert ai_search_depth(25_000) == 3


def test_load_ai_knowledge_rebuilds_stale_rule_cache(tmp_path: Path) -> None:
    cache = tmp_path / "ai.npz"
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    stale = AiKnowledge(
        type(universe)(
            "stale-fingerprint",
            universe.ringleader,
            universe.hideout,
            universe.occupant_by_city,
            universe.answer0,
            universe.answer1,
            universe.dual_question,
            universe.available_question,
        ),
        encoding,
        full_belief(universe),
    )
    stale.universe.save(cache)

    knowledge = load_ai_knowledge(BIRD_RULES, cache)

    assert knowledge.universe.rules_fingerprint == rules_fingerprint(BIRD_RULES)
    assert knowledge.universe.board_count > universe.board_count


def test_ai_only_buys_extra_accusation_for_campaign_critical_win() -> None:
    knowledge = _knowledge_with_one_pair()

    ordinary_round = _ai_post_action_state(100_000, 100_000)
    assert not should_buy_extra_for_accusation(ordinary_round, knowledge)

    campaign_point = _ai_post_action_state(CAMPAIGN_TARGET, 100_000)
    assert should_buy_extra_for_accusation(campaign_point, knowledge)


def test_tempo_buys_extra_action_for_any_definitive_accusation() -> None:
    knowledge = _knowledge_with_one_pair()

    assert should_buy_tempo_extra(_ai_post_action_state(100_000, 100_000), knowledge)


def test_ai_accuses_instead_of_asking_again_with_two_pairs() -> None:
    encoding = Encoding(BIRD_RULES)
    answers = np.zeros((encoding.question_count, 2), dtype=np.uint8)
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    universe = Universe(
        "test",
        np.asarray([0, 1], dtype=np.uint8),
        np.asarray([0, 1], dtype=np.uint8),
        np.zeros((2, len(BIRD_RULES.cities)), dtype=np.uint8),
        answers,
        answers,
        np.zeros(encoding.question_count, dtype=np.uint8),
        available,
    )
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))

    assert isinstance(recommended_action(knowledge), PairCandidate)


def test_ai_asks_an_informative_question_instead_of_opening_accusation() -> None:
    encoding = Encoding(BIRD_RULES)
    board_count = len(BIRD_RULES.spies) * len(BIRD_RULES.cities)
    answers = np.zeros((encoding.question_count, board_count), dtype=np.uint8)
    answers[0, board_count // 2 :] = 1
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    universe = Universe(
        "test",
        np.repeat(np.arange(9, dtype=np.uint8), 9),
        np.tile(np.arange(9, dtype=np.uint8), 9),
        np.zeros((board_count, len(BIRD_RULES.cities)), dtype=np.uint8),
        answers,
        answers,
        np.zeros(encoding.question_count, dtype=np.uint8),
        available,
    )
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))

    assert isinstance(recommended_action(knowledge), Question)


def test_ai_accuses_with_indistinguishable_pairs() -> None:
    encoding = Encoding(BIRD_RULES)
    for count in range(3, 10):
        answers = np.zeros((encoding.question_count, count), dtype=np.uint8)
        available = np.zeros(encoding.question_count, dtype=np.uint8)
        available[0] = 1
        ids = np.arange(count, dtype=np.uint8)
        universe = Universe(
            "test",
            ids,
            ids,
            np.zeros((count, len(BIRD_RULES.cities)), dtype=np.uint8),
            answers,
            answers,
            np.zeros(encoding.question_count, dtype=np.uint8),
            available,
        )
        knowledge = AiKnowledge(universe, encoding, full_belief(universe))

        assert isinstance(recommended_action(knowledge), PairCandidate)


def test_ai_asks_when_question_distinguishes_layouts_but_not_pairs_yet() -> None:
    encoding = Encoding(BIRD_RULES)
    answers = np.asarray([[0, 1, 0, 1]], dtype=np.uint8)
    answers = np.repeat(answers, encoding.question_count, axis=0)
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    universe = Universe(
        "test",
        np.asarray([0, 0, 1, 1], dtype=np.uint8),
        np.asarray([0, 0, 1, 1], dtype=np.uint8),
        np.zeros((4, len(BIRD_RULES.cities)), dtype=np.uint8),
        answers,
        answers,
        np.zeros(encoding.question_count, dtype=np.uint8),
        available,
    )
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))

    assert isinstance(recommended_action(knowledge), Question)


def test_wrong_ai_accusation_eliminates_one_of_three_pairs() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    belief = full_belief(universe)
    selected = []
    seen_pairs: set[tuple[int, int]] = set()
    for board in belief:
        pair = (int(universe.ringleader[board]), int(universe.hideout[board]))
        if pair not in seen_pairs:
            selected.append(board)
            seen_pairs.add(pair)
        if len(selected) == 3:
            break
    knowledge = AiKnowledge(universe, encoding, belief[selected])

    action = PairCandidate(
        int(universe.ringleader[selected[0]]),
        int(universe.hideout[selected[0]]),
        1,
    )
    after = observe_accusation(
        knowledge,
        BIRD_RULES.spies[action.ringleader].id,
        BIRD_RULES.cities[action.hideout].id,
        correct=False,
    )

    assert len(pair_candidates(after.universe, after.belief)) == 2


def test_defensive_board_preserves_ringleader_and_varies_by_seed() -> None:
    ringleader = SEA_RULES.spies[0].id
    boards = [choose_defensive_board(SEA_RULES, ringleader, Random(seed)) for seed in range(4)]

    assert len(set(boards)) > 1
    for board in boards:
        assert board.ringleader == ringleader
        validate_board(SEA_RULES, board)
