from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from spyweb.core.model import Answer, Question, Rules
from spyweb.core.rules import rules_fingerprint
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


@dataclass(frozen=True)
class AiKnowledge:
    universe: Universe
    encoding: Encoding
    belief: Belief


def load_ai_knowledge(rules: Rules, cache: Path) -> AiKnowledge:
    encoding = Encoding(rules)
    expected = universe_board_count(rules)
    if cache.exists():
        universe = Universe.load(
            cache,
            expected_rules_fingerprint=rules_fingerprint(rules),
            expected_board_count=expected,
        )
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


def accusation_candidate(knowledge: AiKnowledge) -> PairCandidate | None:
    candidates = pair_candidates(knowledge.universe, knowledge.belief)
    return candidates[0] if len(candidates) == 1 else None


def recommended_question(knowledge: AiKnowledge) -> Question:
    recommendation = recommend_questions(knowledge.universe, knowledge.belief)
    return knowledge.encoding.decode_question(recommendation.best.immediate.question)


def should_buy_second(knowledge: AiKnowledge, question: Question, first: Answer) -> bool:
    qid = knowledge.encoding.question_id(question)
    first_code = knowledge.encoding.answer_code(first)
    option = next(
        option
        for option in score_dual_payment(knowledge.universe, knowledge.belief, qid)
        if option.first == first_code
    )
    return option.paid_worst_pairs < option.no_pay_pairs
