from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    Accusation,
    AskedQuestion,
    accuse,
    ask_question,
    legal_questions,
    new_game,
)
from spyweb.core.rules import validate_board


def test_new_game_is_reproducible_and_boards_are_valid() -> None:
    first = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=42)
    second = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=42)

    assert first == second
    validate_board(BIRD_RULES, first.players[0].board)
    validate_board(SEA_RULES, first.players[1].board)


def test_asking_resolves_against_opponent_and_passes_turn() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=7)
    question = legal_questions(SEA_RULES)[0]

    next_state = ask_question(state, question)

    assert next_state.turn == 1
    assert isinstance(next_state.history[-1], AskedQuestion)


def test_correct_accusation_wins_and_wrong_accusation_passes() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=9)
    target = state.opponent.board

    won = accuse(state, target.ringleader, target.hideout)
    assert won.winner == 0
    assert isinstance(won.history[-1], Accusation)

    wrong_ringleader = SEA_RULES.spies[(int(target.ringleader) + 1) % len(SEA_RULES.spies)].id
    missed = accuse(state, wrong_ringleader, target.hideout)
    assert missed.winner is None
    assert missed.turn == 1
