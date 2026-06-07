from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random

from spyweb.core.game import ACTION_COST, CAMPAIGN_TARGET, GameState, legal_questions
from spyweb.core.model import (
    Answer,
    Board,
    CityId,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Rules,
    SpyAnswer,
    SpyId,
)
from spyweb.core.rules import answer_question, rules_fingerprint, validate_board
from spyweb.solver.belief import (
    Belief,
    PairCandidate,
    filter_first_answer,
    filter_paid_second,
    full_belief,
    pair_candidates,
    score_dual_payment,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.policy import recommend_questions
from spyweb.solver.universe import Universe, build_universe, universe_board_count

AI_TWO_PLY_MAX_BOARDS = 250_000
AI_THREE_PLY_MAX_BOARDS = 25_000
AI_MINIMAX_BRANCHING = 5
AI_DEFENSIVE_LAYOUT_SAMPLES = 1_024
AI_DEFENSIVE_LAYOUT_POOL = 32


@dataclass(frozen=True)
class AiKnowledge:
    universe: Universe
    encoding: Encoding
    belief: Belief


def _random_board_for_ringleader(rules: Rules, ringleader: SpyId, random: Random) -> Board:
    occupants: list[SpyId | None] = [spy.id for spy in rules.spies if spy.id != ringleader]
    occupants.append(None)
    random.shuffle(occupants)
    hideout = next(
        city.id for city, occupant in zip(rules.cities, occupants, strict=True) if occupant is None
    )
    board = Board(ringleader, hideout, tuple(occupants))
    validate_board(rules, board)
    return board


def _defensive_layout_score(rules: Rules, board: Board) -> tuple[int, int]:
    answers = [
        answer
        for question in legal_questions(rules)
        for answer in answer_question(rules, board, question)
    ]
    nothing = sum(isinstance(answer, NothingAnswer) for answer in answers)
    spy_answers = sum(isinstance(answer, SpyAnswer) for answer in answers)
    landmarks = sum(isinstance(answer, LandmarkAnswer) for answer in answers)
    # "Nothing" is usually the broadest answer bucket; landmarks are usually
    # strong absolute anchors. This is a cheap setup heuristic, not solve-tree value.
    return (nothing * 4 + spy_answers - landmarks * 3, nothing)


def choose_defensive_board(rules: Rules, ringleader: SpyId, random: Random) -> Board:
    candidates = [
        _random_board_for_ringleader(rules, ringleader, random)
        for _ in range(AI_DEFENSIVE_LAYOUT_SAMPLES)
    ]
    candidates.sort(key=lambda board: _defensive_layout_score(rules, board), reverse=True)
    pool_size = min(AI_DEFENSIVE_LAYOUT_POOL, len(candidates))
    return candidates[random.randrange(pool_size)]


def load_ai_knowledge(rules: Rules, cache: Path) -> AiKnowledge:
    encoding = Encoding(rules)
    expected = universe_board_count(rules)
    if cache.exists():
        try:
            universe = Universe.load(
                cache,
                expected_rules_fingerprint=rules_fingerprint(rules),
                expected_board_count=expected,
            )
        except ValueError as error:
            message = str(error)
            stale_cache = (
                "different rules" in message or "Unsupported universe cache version" in message
            )
            if not stale_cache:
                raise
            universe = build_universe(rules, encoding)
            universe.save(cache)
    else:
        universe = build_universe(rules, encoding)
        universe.save(cache)
    return AiKnowledge(universe, encoding, full_belief(universe))


def reset_ai_knowledge(knowledge: AiKnowledge) -> AiKnowledge:
    return AiKnowledge(knowledge.universe, knowledge.encoding, full_belief(knowledge.universe))


def observe_first(knowledge: AiKnowledge, question: Question, answer: Answer) -> AiKnowledge:
    belief = filter_first_answer(
        knowledge.universe,
        knowledge.belief,
        knowledge.encoding.question_id(question),
        knowledge.encoding.answer_code(answer),
    )
    return AiKnowledge(knowledge.universe, knowledge.encoding, belief)


def observe_second(
    knowledge: AiKnowledge, question: Question, first: Answer, second: Answer
) -> AiKnowledge:
    belief = filter_paid_second(
        knowledge.universe,
        knowledge.belief,
        knowledge.encoding.question_id(question),
        knowledge.encoding.answer_code(first),
        knowledge.encoding.answer_code(second),
    )
    return AiKnowledge(knowledge.universe, knowledge.encoding, belief)


def observe_accusation(
    knowledge: AiKnowledge, ringleader: SpyId, hideout: CityId, *, correct: bool
) -> AiKnowledge:
    universe = knowledge.universe
    belief = knowledge.belief
    matches = (universe.ringleader[belief] == ringleader) & (universe.hideout[belief] == hideout)
    return AiKnowledge(universe, knowledge.encoding, belief[matches if correct else ~matches])


def accusation_candidate(knowledge: AiKnowledge) -> PairCandidate | None:
    candidates = pair_candidates(knowledge.universe, knowledge.belief)
    return candidates[0] if len(candidates) == 1 else None


def recommended_action(knowledge: AiKnowledge) -> PairCandidate | Question:
    candidates = pair_candidates(knowledge.universe, knowledge.belief)
    if len(candidates) == 1:
        return candidates[0]

    depth = ai_search_depth(int(knowledge.belief.size))
    recommendation = recommend_questions(
        knowledge.universe,
        knowledge.belief,
        depth=depth,
        max_lookahead_boards=int(knowledge.belief.size),
        branching_limit=AI_MINIMAX_BRANCHING,
    )
    if recommendation.best.immediate.worst_pairs >= len(candidates):
        return max(candidates, key=lambda candidate: candidate.boards)
    return knowledge.encoding.decode_question(recommendation.best.immediate.question)


def ai_search_depth(board_count: int) -> int:
    if board_count <= AI_THREE_PLY_MAX_BOARDS:
        return 3
    if board_count <= AI_TWO_PLY_MAX_BOARDS:
        return 2
    return 1


def recommended_question(knowledge: AiKnowledge) -> Question:
    action = recommended_action(knowledge)
    if isinstance(action, PairCandidate):
        raise ValueError("The recommended action is an accusation")
    return action


def _campaign_money_after_immediate_win(
    state: GameState, *, payments: int, bounty: int
) -> tuple[int, int]:
    actor_money = state.actor.money - payments + bounty
    opponent_money = state.opponent.money + payments
    return actor_money, opponent_money


def _immediate_win_is_campaign_critical(state: GameState, *, payments: int, bounty: int) -> bool:
    actor_money, opponent_money = _campaign_money_after_immediate_win(
        state, payments=payments, bounty=bounty
    )
    wins_campaign = actor_money >= CAMPAIGN_TARGET and actor_money > opponent_money
    prevents_campaign_loss = state.opponent.money >= CAMPAIGN_TARGET and (
        opponent_money < CAMPAIGN_TARGET or actor_money >= opponent_money
    )
    return wins_campaign or prevents_campaign_loss


def should_buy_extra_for_accusation(state: GameState, knowledge: AiKnowledge) -> bool:
    candidate = accusation_candidate(knowledge)
    if candidate is None or state.extra_action_bought or state.actor.money < ACTION_COST:
        return False
    bounty = state.opponent.rules.spies[candidate.ringleader].bounty
    return _immediate_win_is_campaign_critical(state, payments=ACTION_COST, bounty=bounty)


def should_buy_second(
    state: GameState, knowledge: AiKnowledge, question: Question, first: Answer
) -> bool:
    qid = knowledge.encoding.question_id(question)
    first_code = knowledge.encoding.answer_code(first)
    option = next(
        option
        for option in score_dual_payment(knowledge.universe, knowledge.belief, qid)
        if option.first == first_code
    )
    if option.no_pay_pairs <= 1 or option.paid_worst_pairs != 1 or state.extra_action_bought:
        return False
    total_payments = ACTION_COST * 2
    if state.actor.money < total_payments:
        return False
    possible_pairs = {
        (
            candidate.ringleader,
            candidate.hideout,
        )
        for partition in option.paid_partitions
        for candidate in pair_candidates(
            knowledge.universe,
            filter_paid_second(
                knowledge.universe,
                knowledge.belief,
                qid,
                option.first,
                partition.second,
            ),
        )
    }
    return bool(possible_pairs) and all(
        _immediate_win_is_campaign_critical(
            state,
            payments=total_payments,
            bounty=state.opponent.rules.spies[ringleader].bounty,
        )
        for ringleader, _ in possible_pairs
    )
