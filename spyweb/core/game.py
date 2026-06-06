from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from random import Random

from spyweb.core.model import Answer, Board, CityId, Question, Rules, Sense, SpyId
from spyweb.core.rules import answer_question, validate_board

ACTION_COST = 100_000
DEFAULT_STARTING_MONEY = 300_000


class TurnPhase(StrEnum):
    ACTION = "action"
    DUAL_SECOND_ANSWER = "dual_second_answer"
    POST_ACTION = "post_action"


@dataclass(frozen=True)
class PlayerState:
    name: str
    rules: Rules
    board: Board
    money: int


@dataclass(frozen=True)
class AskedQuestion:
    asker: int
    question: Question
    answer: Answer


@dataclass(frozen=True)
class BoughtSecondAnswer:
    asker: int
    question: Question
    answer: Answer
    cost: int = ACTION_COST


@dataclass(frozen=True)
class Accusation:
    accuser: int
    ringleader: SpyId
    hideout: CityId
    correct: bool


@dataclass(frozen=True)
class BoughtExtraAction:
    actor: int
    cost: int = ACTION_COST


@dataclass(frozen=True)
class EndedTurn:
    actor: int


GameEvent = AskedQuestion | BoughtSecondAnswer | Accusation | BoughtExtraAction | EndedTurn


@dataclass(frozen=True)
class PendingSecondAnswer:
    asker: int
    question: Question
    answer: Answer


@dataclass(frozen=True)
class GameState:
    players: tuple[PlayerState, PlayerState]
    turn: int = 0
    phase: TurnPhase = TurnPhase.ACTION
    pending_second: PendingSecondAnswer | None = None
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
    starting_money: int = DEFAULT_STARTING_MONEY,
) -> GameState:
    if starting_money < 0:
        raise ValueError("Starting money cannot be negative")
    random = Random(seed)
    return GameState(
        (
            PlayerState(first_name, first_rules, random_board(first_rules, random), starting_money),
            PlayerState(
                second_name, second_rules, random_board(second_rules, random), starting_money
            ),
        )
    )


def legal_questions(rules: Rules) -> tuple[Question, ...]:
    return tuple(
        Question(spy.id, sense) for spy in rules.spies for sense in Sense if spy.directions[sense]
    )


def _require_action(state: GameState) -> None:
    if state.winner is not None:
        raise ValueError("Game is already over")
    if state.phase is not TurnPhase.ACTION:
        raise ValueError(f"Cannot take an action during {state.phase.value}")


def _transfer_to_opponent(state: GameState, amount: int) -> tuple[PlayerState, PlayerState]:
    if state.actor.money < amount:
        raise ValueError(f"{state.actor.name} cannot afford ${amount:,}")
    players = list(state.players)
    players[state.turn] = replace(state.actor, money=state.actor.money - amount)
    players[1 - state.turn] = replace(state.opponent, money=state.opponent.money + amount)
    return players[0], players[1]


def ask_question(state: GameState, question: Question, *, first_answer_index: int = 0) -> GameState:
    _require_action(state)
    answers = answer_question(state.opponent.rules, state.opponent.board, question)
    if first_answer_index < 0 or first_answer_index >= len(answers):
        raise ValueError("Invalid first answer choice")
    first = answers[first_answer_index]
    event = AskedQuestion(state.turn, question, first)
    if len(answers) == 1:
        return replace(state, phase=TurnPhase.POST_ACTION, history=(*state.history, event))
    second = answers[1 - first_answer_index]
    return replace(
        state,
        phase=TurnPhase.DUAL_SECOND_ANSWER,
        pending_second=PendingSecondAnswer(state.turn, question, second),
        history=(*state.history, event),
    )


def decline_second_answer(state: GameState) -> GameState:
    if state.phase is not TurnPhase.DUAL_SECOND_ANSWER:
        raise ValueError("There is no second answer to decline")
    return replace(state, phase=TurnPhase.POST_ACTION, pending_second=None)


def buy_second_answer(state: GameState) -> GameState:
    if state.phase is not TurnPhase.DUAL_SECOND_ANSWER or state.pending_second is None:
        raise ValueError("There is no second answer to buy")
    pending = state.pending_second
    players = _transfer_to_opponent(state, ACTION_COST)
    event = BoughtSecondAnswer(state.turn, pending.question, pending.answer)
    return replace(
        state,
        players=players,
        phase=TurnPhase.POST_ACTION,
        pending_second=None,
        history=(*state.history, event),
    )


def accuse(state: GameState, ringleader: SpyId, hideout: CityId) -> GameState:
    _require_action(state)
    board = state.opponent.board
    correct = board.ringleader == ringleader and board.hideout == hideout
    event = Accusation(state.turn, ringleader, hideout, correct)
    return replace(
        state,
        phase=TurnPhase.POST_ACTION,
        winner=state.turn if correct else None,
        history=(*state.history, event),
    )


def buy_extra_action(state: GameState) -> GameState:
    if state.phase is not TurnPhase.POST_ACTION:
        raise ValueError("An extra action can only be bought after an action")
    if state.winner is not None:
        raise ValueError("Game is already over")
    players = _transfer_to_opponent(state, ACTION_COST)
    event = BoughtExtraAction(state.turn)
    return replace(
        state,
        players=players,
        phase=TurnPhase.ACTION,
        history=(*state.history, event),
    )


def end_turn(state: GameState) -> GameState:
    if state.phase is not TurnPhase.POST_ACTION:
        raise ValueError("The turn can only end after an action")
    if state.winner is not None:
        raise ValueError("Game is already over")
    event = EndedTurn(state.turn)
    return replace(
        state,
        turn=1 - state.turn,
        phase=TurnPhase.ACTION,
        history=(*state.history, event),
    )
