from dataclasses import replace

from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    CAMPAIGN_TARGET,
    ROUND_SALARY,
    Accusation,
    AskedQuestion,
    BoughtExtraAction,
    BoughtSecondAnswer,
    CampaignState,
    TurnPhase,
    accuse,
    ask_question,
    buy_extra_action,
    buy_second_answer,
    campaign_winner,
    decline_second_answer,
    end_turn,
    legal_questions,
    new_game,
    next_campaign_round,
)
from spyweb.core.model import Direction, Sense
from spyweb.core.rules import validate_board


def test_dual_point_directions_match_transcription() -> None:
    raven = next(spy for spy in BIRD_RULES.spies if spy.name == "Raven")
    urchin = next(spy for spy in SEA_RULES.spies if spy.name == "Urchin")

    assert raven.directions[Sense.POINT] == (Direction.N, Direction.S)
    assert urchin.directions[Sense.POINT] == (Direction.E, Direction.W)


def test_new_game_is_reproducible_and_boards_are_valid() -> None:
    first = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=42)
    second = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=42)

    assert first == second
    validate_board(BIRD_RULES, first.players[0].board)
    validate_board(SEA_RULES, first.players[1].board)


def test_asking_resolves_against_opponent_then_player_ends_turn() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=7)
    question = legal_questions(SEA_RULES)[0]

    next_state = ask_question(state, question)

    assert next_state.turn == 0
    assert next_state.phase is TurnPhase.POST_ACTION
    assert isinstance(next_state.history[-1], AskedQuestion)
    passed = end_turn(next_state)
    assert passed.turn == 1
    assert passed.phase is TurnPhase.ACTION


def test_correct_accusation_wins_and_wrong_accusation_allows_continuation() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=9)
    target = state.opponent.board

    won = accuse(state, target.ringleader, target.hideout)
    assert won.winner == 0
    assert isinstance(won.history[-1], Accusation)

    wrong_ringleader = SEA_RULES.spies[(int(target.ringleader) + 1) % len(SEA_RULES.spies)].id
    missed = accuse(state, wrong_ringleader, target.hideout)
    assert missed.winner is None
    assert missed.turn == 0
    assert missed.phase is TurnPhase.POST_ACTION


def test_paid_extra_action_transfers_money_and_preserves_turn() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=7)
    acted = ask_question(state, legal_questions(SEA_RULES)[0])

    continued = buy_extra_action(acted)

    assert continued.turn == 0
    assert continued.phase is TurnPhase.ACTION
    assert continued.extra_action_bought
    assert continued.players[0].money == 0
    assert continued.players[1].money == 200_000
    assert isinstance(continued.history[-1], BoughtExtraAction)

    acted_again = ask_question(continued, legal_questions(SEA_RULES)[1])
    try:
        buy_extra_action(acted_again)
    except ValueError as error:
        assert str(error) == "Only one extra action may be bought per turn"
    else:
        raise AssertionError("A second extra action purchase in one turn must fail")

    passed = end_turn(acted_again)
    assert not passed.extra_action_bought


def test_urchin_second_point_answer_can_be_bought_or_declined() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=7, starting_money=200_000)
    urchin_point = next(
        question
        for question in legal_questions(SEA_RULES)
        if SEA_RULES.spies[int(question.spy)].name == "Urchin" and question.sense.name == "POINT"
    )

    asked = ask_question(state, urchin_point, first_answer_index=1)
    assert asked.phase is TurnPhase.DUAL_SECOND_ANSWER
    assert asked.pending_second is not None

    bought = buy_second_answer(asked)
    assert bought.phase is TurnPhase.POST_ACTION
    assert bought.players[0].money == 100_000
    assert bought.players[1].money == 300_000
    assert isinstance(bought.history[-1], BoughtSecondAnswer)
    assert not bought.extra_action_bought

    continued = buy_extra_action(bought)
    assert continued.extra_action_bought

    declined = decline_second_answer(asked)
    assert declined.phase is TurnPhase.POST_ACTION
    assert declined.players == asked.players


def test_correct_accusation_awards_ringleader_bounty() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=9)
    target = state.opponent.board
    bounty = state.opponent.rules.spies[int(target.ringleader)].bounty

    won = accuse(state, target.ringleader, target.hideout)

    assert won.actor.money == 100_000 + bounty


def test_next_campaign_round_pays_salary_and_loser_starts() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=9)
    target = state.opponent.board
    won = accuse(state, target.ringleader, target.hideout)

    campaign = next_campaign_round(CampaignState(won))

    assert campaign.round_number == 2
    assert campaign.round.turn == 1
    assert campaign.round.players[0].money == won.players[0].money + ROUND_SALARY
    assert campaign.round.players[1].money == won.players[1].money + ROUND_SALARY


def test_campaign_ends_at_round_end_by_money_or_continues_on_tie() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=9)
    ended = replace(
        state,
        players=(
            replace(state.players[0], money=CAMPAIGN_TARGET),
            state.players[1],
        ),
        winner=0,
    )
    assert campaign_winner(ended) == 0

    tied = replace(
        ended,
        players=(
            replace(ended.players[0], money=CAMPAIGN_TARGET),
            replace(ended.players[1], money=CAMPAIGN_TARGET),
        ),
    )
    assert campaign_winner(tied) is None
