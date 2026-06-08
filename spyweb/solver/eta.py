from __future__ import annotations

from dataclasses import dataclass
from math import log

import numpy as np

from spyweb.core.game import ACTION_COST, CAMPAIGN_TARGET
from spyweb.core.model import Rules
from spyweb.solver.belief import Belief, pair_count, rank_questions
from spyweb.solver.universe import Universe

ETA_RACE_CONFIDENCE_ACTIONS = 3.5


@dataclass(frozen=True)
class SolveEta:
    actions: float
    pairs: int
    best_worst_pairs: int


def estimate_solve_eta(universe: Universe, belief: Belief) -> SolveEta:
    """Estimate worst-case actions remaining, including the final accusation."""
    pairs = pair_count(universe, belief)
    if pairs <= 1:
        return SolveEta(1.0, pairs, pairs)

    informative = tuple(
        score for score in rank_questions(universe, belief) if score.worst_pairs < pairs
    )
    if not informative:
        # With no informative question, sequential accusations are the only progress.
        return SolveEta(float(pairs), pairs, pairs)

    best_worst_pairs = min(score.worst_pairs for score in informative)
    information_per_question = log(pairs / best_worst_pairs)
    estimated_questions = log(pairs) / information_per_question
    return SolveEta(estimated_questions + 1.0, pairs, best_worst_pairs)


def extra_action_changes_race_winner(actor_eta: SolveEta, opponent_eta: SolveEta) -> bool:
    """Return whether buying initiative flips the projected alternating-action race."""
    if max(actor_eta.actions, opponent_eta.actions) > ETA_RACE_CONFIDENCE_ACTIONS:
        return False
    actor_without_buy = actor_eta.actions * 2.0
    opponent_without_buy = opponent_eta.actions * 2.0 - 1.0
    actor_with_buy = actor_eta.actions * 2.0 - 1.0
    opponent_with_buy = opponent_eta.actions * 2.0
    return (
        actor_without_buy >= opponent_without_buy
        and actor_with_buy < opponent_with_buy
    )


def expected_ringleader_bounty(universe: Universe, belief: Belief, rules: Rules) -> float:
    """Return board-weighted expected bounty among the remaining worlds."""
    if not belief.size:
        raise ValueError("Cannot estimate a bounty from an empty belief")
    bounties = np.asarray([spy.bounty for spy in rules.spies], dtype=np.float64)
    return float(np.mean(bounties[universe.ringleader[belief]]))


def extra_action_improves_campaign_outcome(
    *,
    actor_money: int,
    opponent_money: int,
    actor_win_bounty: float,
    opponent_win_bounty: float,
) -> bool:
    """Compare projected campaign outcomes when buying flips the round winner."""

    def utility(actor: float, opponent: float) -> tuple[int, float]:
        if actor >= CAMPAIGN_TARGET and actor > opponent:
            result = 1
        elif opponent >= CAMPAIGN_TARGET and opponent > actor:
            result = -1
        else:
            result = 0
        return result, actor - opponent

    buy = utility(
        actor_money - ACTION_COST + actor_win_bounty,
        opponent_money + ACTION_COST,
    )
    decline = utility(
        actor_money,
        opponent_money + opponent_win_bounty,
    )
    return buy > decline
