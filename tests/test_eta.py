import numpy as np

from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.solver.belief import full_belief
from spyweb.solver.encoding import Encoding
from spyweb.solver.eta import (
    SolveEta,
    estimate_solve_eta,
    expected_ringleader_bounty,
    extra_action_changes_race_winner,
    extra_action_improves_campaign_outcome,
)
from spyweb.solver.universe import Universe


def _eta_universe(*, informative: bool) -> Universe:
    encoding = Encoding(BIRD_RULES)
    answers = np.zeros((encoding.question_count, 4), dtype=np.uint8)
    if informative:
        answers[0] = np.asarray([0, 0, 1, 1], dtype=np.uint8)
    available = np.zeros(encoding.question_count, dtype=np.uint8)
    available[0] = 1
    return Universe(
        "test",
        np.asarray([0, 1, 2, 3], dtype=np.uint8),
        np.asarray([0, 1, 2, 3], dtype=np.uint8),
        np.zeros((4, len(BIRD_RULES.cities)), dtype=np.uint8),
        answers,
        answers,
        np.zeros(encoding.question_count, dtype=np.uint8),
        available,
    )


def test_eta_uses_question_contraction_and_includes_accusation() -> None:
    universe = _eta_universe(informative=True)

    eta = estimate_solve_eta(universe, full_belief(universe))

    assert eta.pairs == 4
    assert eta.best_worst_pairs == 2
    assert eta.actions == 3.0


def test_eta_falls_back_to_sequential_accusations_without_information() -> None:
    universe = _eta_universe(informative=False)

    eta = estimate_solve_eta(universe, full_belief(universe))

    assert eta.actions == 4.0


def test_extra_action_only_buys_when_it_flips_projected_race() -> None:
    tied = SolveEta(3.0, 4, 2)
    ahead = SolveEta(2.0, 4, 2)
    behind = SolveEta(4.0, 4, 2)
    distant_tie = SolveEta(5.0, 20, 10)

    assert extra_action_changes_race_winner(tied, tied)
    assert not extra_action_changes_race_winner(ahead, tied)
    assert not extra_action_changes_race_winner(behind, tied)
    assert not extra_action_changes_race_winner(distant_tie, distant_tie)


def test_expected_bounty_is_weighted_by_remaining_boards() -> None:
    universe = _eta_universe(informative=True)
    belief = np.asarray([0, 0, 1, 2], dtype=np.uint32)
    expected = (
        BIRD_RULES.spies[0].bounty * 2
        + BIRD_RULES.spies[1].bounty
        + BIRD_RULES.spies[2].bounty
    ) / 4

    assert expected_ringleader_bounty(universe, belief, BIRD_RULES) == expected


def test_extra_action_rejects_round_flip_that_worsens_campaign_money() -> None:
    assert not extra_action_improves_campaign_outcome(
        actor_money=100_000,
        opponent_money=100_000,
        actor_win_bounty=100_000,
        opponent_win_bounty=100_000,
    )


def test_extra_action_accepts_valuable_or_campaign_decisive_round_flip() -> None:
    assert extra_action_improves_campaign_outcome(
        actor_money=100_000,
        opponent_money=100_000,
        actor_win_bounty=500_000,
        opponent_win_bounty=SEA_RULES.spies[1].bounty,
    )
    assert extra_action_improves_campaign_outcome(
        actor_money=900_000,
        opponent_money=900_000,
        actor_win_bounty=300_000,
        opponent_win_bounty=500_000,
    )


def test_prior_payment_is_reflected_in_next_purchase_decision() -> None:
    # Current money already includes an earlier $100k transfer. A second purchase
    # can still be rational if it truly flips a 300k-versus-300k round.
    assert extra_action_improves_campaign_outcome(
        actor_money=100_000,
        opponent_money=300_000,
        actor_win_bounty=300_000,
        opponent_win_bounty=300_000,
    )
