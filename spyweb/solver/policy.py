from __future__ import annotations

from dataclasses import dataclass

from spyweb.solver.belief import (
    Belief,
    QuestionScore,
    filter_first_answer,
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
) -> tuple[int, int]:
    current = (pair_count(universe, belief), int(belief.size))
    if depth == 0 or current[0] <= 1:
        return current
    key = (depth, belief.tobytes())
    cached = cache.get(key)
    if cached is not None:
        return cached
    best = min(
        (
            _question_leaf_value(universe, belief, score, depth, cache)
            for score in rank_questions(universe, belief)
        ),
        default=current,
    )
    cache[key] = best
    return best


def _question_leaf_value(
    universe: Universe,
    belief: Belief,
    immediate: QuestionScore,
    depth: int,
    cache: dict[tuple[int, bytes], tuple[int, int]],
) -> tuple[int, int]:
    worst = (0, 0)
    for partition in immediate.partitions:
        bucket = filter_first_answer(universe, belief, immediate.question, partition.answer)
        child = (
            (partition.pairs, partition.boards)
            if bucket.size == belief.size
            else _best_leaf_value(universe, bucket, depth - 1, cache)
        )
        worst = max(worst, child)
    return worst


def recommend_questions(
    universe: Universe,
    belief: Belief,
    *,
    depth: int = 1,
    max_lookahead_boards: int = 10_000,
) -> Recommendation:
    if depth < 1:
        raise ValueError("Policy depth must be at least 1")
    effective_depth = depth if belief.size <= max_lookahead_boards else 1
    cache: dict[tuple[int, bytes], tuple[int, int]] = {}
    scores = tuple(
        sorted(
            (
                PolicyScore(
                    immediate,
                    *_question_leaf_value(universe, belief, immediate, effective_depth, cache),
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
