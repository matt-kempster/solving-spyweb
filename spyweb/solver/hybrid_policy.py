from __future__ import annotations

from dataclasses import dataclass

from spyweb.solver.belief import (
    Belief,
    PairCandidate,
    QuestionScore,
    filter_first_answer,
    pair_candidates,
    pair_count,
    rank_questions,
)
from spyweb.solver.component_policy import Observation, rank_component_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.policy import Recommendation, recommend_questions
from spyweb.solver.universe import Universe

HYBRID_COMPONENT_SHORTLIST = 8
EXACT_ENDGAME_MAX_PAIRS = 5


@dataclass(frozen=True)
class ExactAction:
    actions: int
    question: QuestionScore | None = None
    accusation: PairCandidate | None = None


def _exact_value(
    universe: Universe,
    belief: Belief,
    cache: dict[bytes, int],
) -> int:
    pairs = pair_count(universe, belief)
    if pairs <= 1:
        return 1
    key = belief.tobytes()
    cached = cache.get(key)
    if cached is not None:
        return cached
    best = pairs
    for score in rank_questions(universe, belief):
        children = tuple(
            filter_first_answer(universe, belief, score.question, partition.answer)
            for partition in score.partitions
        )
        if any(child.size == belief.size for child in children):
            continue
        best = min(best, 1 + max(_exact_value(universe, child, cache) for child in children))
    cache[key] = best
    return best


def exact_endgame_action(universe: Universe, belief: Belief) -> ExactAction:
    candidates = pair_candidates(universe, belief)
    if len(candidates) == 1:
        return ExactAction(1, accusation=candidates[0])
    cache: dict[bytes, int] = {}
    best = ExactAction(len(candidates), accusation=max(candidates, key=lambda item: item.boards))
    for score in rank_questions(universe, belief):
        children = tuple(
            filter_first_answer(universe, belief, score.question, partition.answer)
            for partition in score.partitions
        )
        if any(child.size == belief.size for child in children):
            continue
        actions = 1 + max(_exact_value(universe, child, cache) for child in children)
        if actions < best.actions:
            best = ExactAction(actions, question=score)
    return best


def recommend_hybrid_questions(
    universe: Universe,
    encoding: Encoding,
    belief: Belief,
    observations: tuple[Observation, ...],
    *,
    depth: int,
    max_lookahead_boards: int,
    branching_limit: int,
) -> Recommendation:
    component_ranked = rank_component_questions(universe, encoding, belief, observations)
    shortlist = tuple(
        score.immediate for score in component_ranked[:HYBRID_COMPONENT_SHORTLIST]
    )
    return recommend_questions(
        universe,
        belief,
        depth=depth,
        max_lookahead_boards=max_lookahead_boards,
        branching_limit=branching_limit,
        root_questions=shortlist,
    )
