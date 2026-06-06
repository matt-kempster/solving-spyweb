from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from spyweb.core.model import Answer, Board, CityId, Question, Rules, Sense, SpyId
from spyweb.core.rules import answer_question, validate_board


@dataclass(frozen=True)
class PlayerState:
    name: str
    rules: Rules
    board: Board


@dataclass(frozen=True)
class AskedQuestion:
    asker: int
    question: Question
    answer: Answer


@dataclass(frozen=True)
class Accusation:
    accuser: int
    ringleader: SpyId
    hideout: CityId
    correct: bool


GameEvent = AskedQuestion | Accusation


@dataclass(frozen=True)
class GameState:
    players: tuple[PlayerState, PlayerState]
    turn: int = 0
    winner: int | None = None
    history: tuple[GameEvent, ...] = ()

    @property
    def actor(self) -> PlayerState:
        return self.players[self.turn]

    @property
    def opponent(self) -> PlayerState:
        return self.players[1 - self.turn]


def random_board(rules: Rules, random: Random) -> Board:
    ringleader = SpyId(random.randrange(len(rules.spies)))
    hideout = CityId(random.randrange(len(rules.cities)))
    visible = [spy.id for spy in rules.spies if spy.id != ringleader]
    random.shuffle(visible)
    occupants: list[SpyId | None] = []
    cursor = 0
    for city in rules.cities:
        if city.id == hideout:
            occupants.append(None)
        else:
            occupants.append(visible[cursor])
            cursor += 1
    board = Board(ringleader, hideout, tuple(occupants))
    validate_board(rules, board)
    return board


def new_game(
    first_name: str,
    first_rules: Rules,
    second_name: str,
    second_rules: Rules,
    *,
    seed: int | None = None,
) -> GameState:
    random = Random(seed)
    return GameState(
        (
            PlayerState(first_name, first_rules, random_board(first_rules, random)),
            PlayerState(second_name, second_rules, random_board(second_rules, random)),
        )
    )


def legal_questions(rules: Rules) -> tuple[Question, ...]:
    return tuple(
        Question(spy.id, sense)
        for spy in rules.spies
        for sense in Sense
        if spy.directions[sense]
    )


def ask_question(state: GameState, question: Question) -> GameState:
    if state.winner is not None:
        raise ValueError("Game is already over")
    answers = answer_question(state.opponent.rules, state.opponent.board, question)
    event = AskedQuestion(state.turn, question, answers[0])
    return replace(state, turn=1 - state.turn, history=(*state.history, event))


def accuse(state: GameState, ringleader: SpyId, hideout: CityId) -> GameState:
    if state.winner is not None:
        raise ValueError("Game is already over")
    board = state.opponent.board
    correct = board.ringleader == ringleader and board.hideout == hideout
    event = Accusation(state.turn, ringleader, hideout, correct)
    return replace(
        state,
        turn=state.turn if correct else 1 - state.turn,
        winner=state.turn if correct else None,
        history=(*state.history, event),
    )
