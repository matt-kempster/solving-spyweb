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
from spyweb.solver.universe import Universe


@dataclass(frozen=True)
class PolicyScore:
    immediate: QuestionScore
    worst_leaf_pairs: int
    worst_leaf_boards: int


@dataclass(frozen=True)
class Recommendation:
    requested_depth: int
    effective_depth: int
    scores: tuple[PolicyScore, ...]

    @property
    def best(self) -> PolicyScore:
        return self.scores[0]


def _best_leaf_value(
    universe: Universe,
    belief: Belief,
    depth: int,
    cache: dict[tuple[int, bytes], tuple[int, int]],
    branching_limit: int | None,
) -> tuple[int, int]:
    current = (pair_count(universe, belief), int(belief.size))
    if depth == 0 or current[0] <= 1:
        return current
    key = (depth, belief.tobytes())
    cached = cache.get(key)
    if cached is not None:
        return cached
    best_question = min(
        (
            _question_leaf_value(universe, belief, score, depth, cache, branching_limit)
            for score in _limited_questions(universe, belief, branching_limit)
        ),
        default=current,
    )
    accusation = best_accusation_leaf_value(
        universe, belief, depth=depth, cache=cache, branching_limit=branching_limit
    )
    best = min(best_question, accusation[1] if accusation is not None else current)
    cache[key] = best
    return best


def _question_leaf_value(
    universe: Universe,
    belief: Belief,
    immediate: QuestionScore,
    depth: int,
    cache: dict[tuple[int, bytes], tuple[int, int]],
    branching_limit: int | None,
) -> tuple[int, int]:
    worst = (0, 0)
    for partition in immediate.partitions:
        bucket = filter_first_answer(universe, belief, immediate.question, partition.answer)
        child = (
            (partition.pairs, partition.boards)
            if bucket.size == belief.size
            else _best_leaf_value(universe, bucket, depth - 1, cache, branching_limit)
        )
        worst = max(worst, child)
    return worst


def _belief_without_pair(
    universe: Universe, belief: Belief, candidate: PairCandidate
) -> tuple[Belief, Belief]:
    matches = (universe.ringleader[belief] == candidate.ringleader) & (
        universe.hideout[belief] == candidate.hideout
    )
    return belief[matches], belief[~matches]


def best_accusation_leaf_value(
    universe: Universe,
    belief: Belief,
    *,
    depth: int,
    cache: dict[tuple[int, bytes], tuple[int, int]] | None = None,
    branching_limit: int | None = None,
) -> tuple[PairCandidate, tuple[int, int]] | None:
    candidates = pair_candidates(universe, belief)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0], (1, candidates[0].boards)
    if branching_limit is not None:
        candidates = tuple(
            sorted(candidates, key=lambda candidate: candidate.boards, reverse=True)[
                :branching_limit
            ]
        )
    local_cache = cache if cache is not None else {}
    best: tuple[PairCandidate, tuple[int, int]] | None = None
    for candidate in candidates:
        correct, wrong = _belief_without_pair(universe, belief, candidate)
        correct_value = (1, int(correct.size))
        wrong_value = (
            (pair_count(universe, wrong), int(wrong.size))
            if depth <= 1
            else _best_leaf_value(universe, wrong, depth - 1, local_cache, branching_limit)
        )
        value = max(correct_value, wrong_value)
        if best is None or value < best[1]:
            best = (candidate, value)
    return best


def _limited_questions(
    universe: Universe, belief: Belief, branching_limit: int | None
) -> tuple[QuestionScore, ...]:
    ranked = rank_questions(universe, belief)
    return ranked if branching_limit is None else ranked[:branching_limit]


def recommend_questions(
    universe: Universe,
    belief: Belief,
    *,
    depth: int = 1,
    max_lookahead_boards: int = 10_000,
    branching_limit: int | None = None,
) -> Recommendation:
    if depth < 1:
        raise ValueError("Policy depth must be at least 1")
    if branching_limit is not None and branching_limit < 1:
        raise ValueError("Branching limit must be at least 1")
    effective_depth = depth if belief.size <= max_lookahead_boards else 1
    cache: dict[tuple[int, bytes], tuple[int, int]] = {}
    scores = tuple(
        sorted(
            (
                PolicyScore(
                    immediate,
                    *_question_leaf_value(
                        universe,
                        belief,
                        immediate,
                        effective_depth,
                        cache,
                        branching_limit,
                    ),
                )
                for immediate in rank_questions(universe, belief)
            ),
            key=lambda score: (
                score.worst_leaf_pairs,
                score.worst_leaf_boards,
                score.immediate.worst_pairs,
                score.immediate.worst_boards,
            ),
        )
    )
    return Recommendation(depth, effective_depth, scores)
