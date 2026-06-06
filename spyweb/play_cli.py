from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    Accusation,
    AskedQuestion,
    GameState,
    accuse,
    ask_question,
    legal_questions,
    new_game,
)
from spyweb.core.model import Answer, LandmarkAnswer, NothingAnswer, Rules, SpyAnswer


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-player hot-seat Spy Web emulator")
    parser.add_argument("--seed", type=int, help="reproducible random setup")
    parser.add_argument(
        "--no-clear", action="store_true", help="do not clear between private turns"
    )
    return parser.parse_args(argv)


def _clear() -> None:
    os.system("clear")


def _answer_label(rules: Rules, answer: Answer) -> str:
    if isinstance(answer, NothingAnswer):
        return "Nothing"
    if isinstance(answer, SpyAnswer):
        return rules.spies[int(answer.spy)].name
    if isinstance(answer, LandmarkAnswer):
        return rules.landmarks[int(answer.landmark)].name
    raise TypeError(answer)


def _board_lines(rules: Rules, state: GameState) -> tuple[str, ...]:
    board = state.actor.board
    cells: list[str] = []
    for city in rules.cities:
        occupant = board.occupant_by_city[int(city.id)]
        label = "HIDEOUT" if occupant is None else rules.spies[int(occupant)].name
        cells.append(f"{city.name}\n{label}")
    width = max(len(line) for cell in cells for line in cell.splitlines()) + 2
    rows: list[str] = []
    for row in range(3):
        row_cells = cells[row * 3 : row * 3 + 3]
        city_line = " | ".join(cell.splitlines()[0].center(width) for cell in row_cells)
        spy_line = " | ".join(cell.splitlines()[1].center(width) for cell in row_cells)
        rows.extend((city_line, spy_line))
        if row < 2:
            rows.append("-+-".join("-" * width for _ in range(3)))
    return tuple(rows)


def _show_private_turn(state: GameState) -> None:
    actor = state.actor
    print(f"{actor.name}'s turn ({actor.rules.spies[0].faction.value.title()})")
    print(f"Your hidden ringleader: {actor.rules.spies[int(actor.board.ringleader)].name}")
    print(f"Your hideout: {actor.rules.cities[int(actor.board.hideout)].name}\n")
    print("\n".join(_board_lines(actor.rules, state)))
    if state.history:
        event = state.history[-1]
        if isinstance(event, AskedQuestion):
            asker = state.players[event.asker]
            target_rules = state.players[1 - event.asker].rules
            question_spy = target_rules.spies[int(event.question.spy)].name
            answer = _answer_label(target_rules, event.answer)
            print(
                f"\nLast action: {asker.name} asked {question_spy} "
                f"{event.question.sense.name.lower()} -> {answer}"
            )
        elif isinstance(event, Accusation):
            accuser = state.players[event.accuser]
            print(f"\nLast action: {accuser.name}'s accusation was incorrect")


def _number(prompt: str, maximum: int) -> int:
    raw = input(prompt).strip()
    value = int(raw)
    if value < 1 or value > maximum:
        raise ValueError(f"Choose a number from 1 to {maximum}")
    return value - 1


def _ask(state: GameState) -> GameState:
    opponent = state.opponent
    questions = legal_questions(opponent.rules)
    print(f"\nQuestions for {opponent.name}:")
    for index, question in enumerate(questions, start=1):
        spy = opponent.rules.spies[int(question.spy)]
        print(f"  {index:2}. {spy.name} {question.sense.name.lower()}")
    question = questions[_number("Question number: ", len(questions))]
    next_state = ask_question(state, question)
    event = next_state.history[-1]
    assert isinstance(event, AskedQuestion)
    print(f"Answer: {_answer_label(opponent.rules, event.answer)}")
    input("\nPress Enter to pass the terminal...")
    return next_state


def _accuse(state: GameState) -> GameState:
    opponent = state.opponent
    print(f"\nRingleaders for {opponent.name}:")
    for index, spy in enumerate(opponent.rules.spies, start=1):
        print(f"  {index}. {spy.name}")
    ringleader = opponent.rules.spies[_number("Ringleader number: ", len(opponent.rules.spies))].id
    print("\nHideouts:")
    for index, city in enumerate(opponent.rules.cities, start=1):
        print(f"  {index}. {city.name}")
    hideout = opponent.rules.cities[_number("Hideout number: ", len(opponent.rules.cities))].id
    next_state = accuse(state, ringleader, hideout)
    event = next_state.history[-1]
    assert isinstance(event, Accusation)
    print("Correct!" if event.correct else "Incorrect.")
    if not event.correct:
        input("\nPress Enter to pass the terminal...")
    return next_state


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    first = input("Bird player name [Bird]: ").strip() or "Bird"
    second = input("Sea player name [Sea]: ").strip() or "Sea"
    state = new_game(first, BIRD_RULES, second, SEA_RULES, seed=args.seed)
    while state.winner is None:
        if not args.no_clear:
            _clear()
        input(f"{state.actor.name}, press Enter when only you can see the terminal...")
        if not args.no_clear:
            _clear()
        _show_private_turn(state)
        command = input("\n[a]sk, a[c]cuse, [q]uit: ").strip().lower()
        try:
            if command == "a":
                state = _ask(state)
            elif command == "c":
                state = _accuse(state)
            elif command == "q":
                return
        except (ValueError, IndexError) as error:
            print(error)
            input("Press Enter to continue...")
    winner = state.players[state.winner]
    print(f"\n{winner.name} wins!")


def main() -> None:
    run()
