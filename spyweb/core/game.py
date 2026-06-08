from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from random import Random

from spyweb.core.model import Answer, Board, CityId, Question, Rules, Sense, SpyId
from spyweb.core.rules import answer_question, validate_board

ACTION_COST = 100_000
DEFAULT_STARTING_MONEY = 100_000
ROUND_SALARY = 100_000
CAMPAIGN_TARGET = 1_000_000


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
    extra_action_bought: bool = False
    pending_second: PendingSecondAnswer | None = None
    winner: int | None = None
    history: tuple[GameEvent, ...] = ()

    @property
    def actor(self) -> PlayerState:
        return self.players[self.turn]

    @property
    def opponent(self) -> PlayerState:
        return self.players[1 - self.turn]


@dataclass(frozen=True)
class CampaignState:
    round: GameState
    round_number: int = 1
    winner: int | None = None


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
    players = state.players
    if correct:
        bounty = state.opponent.rules.spies[int(board.ringleader)].bounty
        awarded = replace(state.actor, money=state.actor.money + bounty)
        players = (awarded, state.opponent) if state.turn == 0 else (state.opponent, awarded)
    return replace(
        state,
        players=players,
        phase=TurnPhase.POST_ACTION,
        winner=state.turn if correct else None,
        history=(*state.history, event),
    )


def buy_extra_action(state: GameState) -> GameState:
    if state.phase is not TurnPhase.POST_ACTION:
        raise ValueError("An extra action can only be bought after an action")
    if state.winner is not None:
        raise ValueError("Game is already over")
    if state.extra_action_bought:
        raise ValueError("Only one extra action may be bought per turn")
    players = _transfer_to_opponent(state, ACTION_COST)
    event = BoughtExtraAction(state.turn)
    return replace(
        state,
        players=players,
        phase=TurnPhase.ACTION,
        extra_action_bought=True,
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
        extra_action_bought=False,
        history=(*state.history, event),
    )


def new_campaign(
    first_name: str,
    first_rules: Rules,
    second_name: str,
    second_rules: Rules,
    *,
    seed: int | None = None,
) -> CampaignState:
    return CampaignState(new_game(first_name, first_rules, second_name, second_rules, seed=seed))


def campaign_winner(state: GameState) -> int | None:
    if state.winner is None:
        raise ValueError("Campaign winner can only be checked at round end")
    first_money, second_money = (player.money for player in state.players)
    if first_money < CAMPAIGN_TARGET and second_money < CAMPAIGN_TARGET:
        return None
    if first_money == second_money:
        return None
    return 0 if first_money > second_money else 1


def next_campaign_round(campaign: CampaignState, *, seed: int | None = None) -> CampaignState:
    state = campaign.round
    if state.winner is None:
        raise ValueError("Cannot start another round before this round is won")
    winner = campaign_winner(state)
    if winner is not None:
        return replace(campaign, winner=winner)
    loser = 1 - state.winner
    random = Random(seed)
    first = replace(
        state.players[0],
        board=random_board(state.players[0].rules, random),
        money=state.players[0].money,
    )
    second = replace(
        state.players[1],
        board=random_board(state.players[1].rules, random),
        money=state.players[1].money,
    )
    return CampaignState(
        GameState((first, second), turn=loser),
        round_number=campaign.round_number + 1,
    )
