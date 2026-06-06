from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from spyweb.ai import (
    AiKnowledge,
    accusation_candidate,
    load_ai_knowledge,
    observe_first,
    observe_second,
    recommended_question,
    reset_ai_knowledge,
    should_buy_second,
)
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    ACTION_COST,
    DEFAULT_STARTING_MONEY,
    Accusation,
    AskedQuestion,
    BoughtExtraAction,
    BoughtSecondAnswer,
    CampaignState,
    EndedTurn,
    GameState,
    TurnPhase,
    accuse,
    ask_question,
    buy_extra_action,
    buy_second_answer,
    decline_second_answer,
    end_turn,
    legal_questions,
    new_game,
    next_campaign_round,
)
from spyweb.core.model import (
    Answer,
    Direction,
    LandmarkAnswer,
    NothingAnswer,
    Rules,
    Sense,
    SpyAnswer,
)
from spyweb.core.rules import answer_question
from spyweb.solver.belief import (
    pair_count,
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-player hot-seat Spy Web emulator")
    parser.add_argument("--seed", type=int, help="reproducible random setup")
    parser.add_argument(
        "--no-clear", action="store_true", help="do not clear between private turns"
    )
    parser.add_argument(
        "--starting-money",
        type=int,
        default=DEFAULT_STARTING_MONEY,
        help=f"starting money per player (default: {DEFAULT_STARTING_MONEY})",
    )
    parser.add_argument("--ai", action="store_true", help="play Bird against a Sea AI")
    parser.add_argument(
        "--ai-cache",
        type=Path,
        default=Path(".cache/play-ai-bird.npz"),
        help="cache for the AI's exact Bird-board universe",
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


def _direction_label(directions: tuple[()] | tuple[Direction] | tuple[Direction, Direction]) -> str:
    return "-" if not directions else "/".join(direction.name for direction in directions)


def _card_lines(rules: Rules) -> tuple[str, ...]:
    return tuple(
        f"  {spy.name:9} look {_direction_label(spy.directions[Sense.LOOK]):3}  "
        f"hear {_direction_label(spy.directions[Sense.HEAR]):3}  "
        f"point {_direction_label(spy.directions[Sense.POINT]):3}"
        for spy in rules.spies
    )


def _knowledge_lines(state: GameState, player: int) -> tuple[str, ...]:
    lines: list[str] = []
    target_rules = state.players[1 - player].rules
    for event in state.history:
        if isinstance(event, AskedQuestion) and event.asker == player:
            spy = target_rules.spies[int(event.question.spy)].name
            lines.append(
                f"  {spy} {event.question.sense.name.lower()} -> "
                f"{_answer_label(target_rules, event.answer)}"
            )
        elif isinstance(event, BoughtSecondAnswer) and event.asker == player:
            spy = target_rules.spies[int(event.question.spy)].name
            lines.append(f"  {spy} second direction -> {_answer_label(target_rules, event.answer)}")
        elif isinstance(event, Accusation) and event.accuser == player:
            spy = target_rules.spies[int(event.ringleader)].name
            city = target_rules.cities[int(event.hideout)].name
            lines.append(f"  Accused {spy} in {city} -> {'correct' if event.correct else 'wrong'}")
    return tuple(lines) or ("  No observations yet.",)


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


def _show_private_turn(state: GameState, ai_knowledge: AiKnowledge | None = None) -> None:
    actor = state.actor
    print(f"{actor.name}'s turn ({actor.rules.spies[0].faction.value.title()})")
    print(f"Money: you ${actor.money:,} | {state.opponent.name} ${state.opponent.money:,}")
    print(f"Your hidden ringleader: {actor.rules.spies[int(actor.board.ringleader)].name}")
    print(f"Your hideout: {actor.rules.cities[int(actor.board.hideout)].name}\n")
    print("\n".join(_board_lines(actor.rules, state)))
    print(f"\n{state.opponent.name}'s card directions:")
    print("\n".join(_card_lines(state.opponent.rules)))
    print("\nYour knowledge base:")
    print("\n".join(_knowledge_lines(state, state.turn)))
    print(f"\n{state.opponent.name}'s knowledge base:")
    print("\n".join(_knowledge_lines(state, 1 - state.turn)))
    if ai_knowledge is not None:
        print(
            f"\nAI solver state: {ai_knowledge.belief.size:,} possible boards, "
            f"{pair_count(ai_knowledge.universe, ai_knowledge.belief)} "
            "possible ringleader/hideout pairs"
        )
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
        elif isinstance(event, BoughtSecondAnswer):
            asker = state.players[event.asker]
            print(f"\nLast action: {asker.name} bought a second direction answer")
        elif isinstance(event, BoughtExtraAction):
            actor = state.players[event.actor]
            print(f"\nLast action: {actor.name} paid for another action")
        elif isinstance(event, EndedTurn):
            actor = state.players[event.actor]
            print(f"\nLast action: {actor.name} ended their turn")


def _number(prompt: str, maximum: int) -> int:
    raw = input(prompt).strip()
    value = int(raw)
    if value < 1 or value > maximum:
        raise ValueError(f"Choose a number from 1 to {maximum}")
    return value - 1


def _handoff(message: str, *, no_clear: bool) -> None:
    input(f"\n{message} Press Enter when ready...")
    if not no_clear:
        _clear()


def _ask(state: GameState, *, no_clear: bool, ai_opponent: bool) -> GameState:
    opponent = state.opponent
    questions = legal_questions(opponent.rules)
    print(f"\nQuestions for {opponent.name}:")
    for index, question in enumerate(questions, start=1):
        spy = opponent.rules.spies[int(question.spy)]
        print(f"  {index:2}. {spy.name} {question.sense.name.lower()}")
    question = questions[_number("Question number: ", len(questions))]
    answers = answer_question(opponent.rules, opponent.board, question)
    first_answer_index = 0
    if len(answers) == 2:
        if ai_opponent:
            first_answer_index = 0
            print(f"{opponent.name} chooses which direction to reveal first.")
        else:
            _handoff(f"Pass the terminal to {opponent.name}.", no_clear=no_clear)
            spy = opponent.rules.spies[int(question.spy)]
            print(f"{state.actor.name} asked what {spy.name} points at.")
            print("Choose which truthful answer to reveal first:")
            for index, answer in enumerate(answers, start=1):
                print(f"  {index}. {_answer_label(opponent.rules, answer)}")
            first_answer_index = _number("First answer number: ", 2)
            _handoff(f"Pass the terminal back to {state.actor.name}.", no_clear=no_clear)

    next_state = ask_question(state, question, first_answer_index=first_answer_index)
    event = next_state.history[-1]
    assert isinstance(event, AskedQuestion)
    print(f"Answer: {_answer_label(opponent.rules, event.answer)}")
    return next_state


def _load_ai_knowledge(cache: Path) -> AiKnowledge:
    cache_existed = cache.exists()
    if cache_existed:
        print(f"Loading AI knowledge from {cache}...")
    else:
        from spyweb.solver.universe import universe_board_count

        expected = universe_board_count(BIRD_RULES)
        print(f"Building the AI's {expected:,}-board knowledge base...")
    knowledge = load_ai_knowledge(BIRD_RULES, cache)
    if not cache_existed:
        print(f"Cached AI knowledge at {cache}")
    return knowledge


def _ai_action(state: GameState, knowledge: AiKnowledge) -> tuple[GameState, AiKnowledge]:
    candidate = accusation_candidate(knowledge)
    if candidate is not None:
        print(
            f"\n{state.actor.name} accuses "
            f"{BIRD_RULES.spies[candidate.ringleader].name} in "
            f"{BIRD_RULES.cities[candidate.hideout].name}."
        )
        return (
            accuse(
                state,
                BIRD_RULES.spies[candidate.ringleader].id,
                BIRD_RULES.cities[candidate.hideout].id,
            ),
            knowledge,
        )

    question = recommended_question(knowledge)
    spy = BIRD_RULES.spies[int(question.spy)]
    print(f"\n{state.actor.name} asks: What does {spy.name} {question.sense.name.lower()} at?")
    answers = answer_question(BIRD_RULES, state.opponent.board, question)
    first_index = 0
    if len(answers) == 2:
        print("Choose which truthful answer to reveal first:")
        for index, answer in enumerate(answers, start=1):
            print(f"  {index}. {_answer_label(BIRD_RULES, answer)}")
        first_index = _number("First answer number: ", 2)
    first = answers[first_index]
    print(f"You answer: {_answer_label(BIRD_RULES, first)}")
    next_state = ask_question(state, question, first_answer_index=first_index)
    return next_state, observe_first(knowledge, question, first)


def _ai_resolve_second(state: GameState, knowledge: AiKnowledge) -> tuple[GameState, AiKnowledge]:
    pending = state.pending_second
    assert pending is not None
    event = state.history[-1]
    assert isinstance(event, AskedQuestion)
    should_buy = state.actor.money >= ACTION_COST and should_buy_second(
        knowledge, pending.question, event.answer
    )
    if not should_buy:
        print(f"{state.actor.name} declines the second answer.")
        return decline_second_answer(state), knowledge
    next_state = buy_second_answer(state)
    second_event = next_state.history[-1]
    assert isinstance(second_event, BoughtSecondAnswer)
    print(
        f"{state.actor.name} pays ${ACTION_COST:,}; second answer: "
        f"{_answer_label(BIRD_RULES, second_event.answer)}"
    )
    return (
        next_state,
        observe_second(knowledge, pending.question, event.answer, second_event.answer),
    )


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
    return next_state


def _resolve_second_answer(state: GameState) -> GameState:
    pending = state.pending_second
    assert pending is not None
    if state.actor.money < ACTION_COST:
        print(f"You cannot afford the ${ACTION_COST:,} second answer.")
        return decline_second_answer(state)
    command = (
        input(f"Pay ${ACTION_COST:,} for the second direction answer? [y/N]: ").strip().lower()
    )
    if command != "y":
        return decline_second_answer(state)
    next_state = buy_second_answer(state)
    event = next_state.history[-1]
    assert isinstance(event, BoughtSecondAnswer)
    print(f"Second answer: {_answer_label(state.opponent.rules, event.answer)}")
    return next_state


def _post_action(state: GameState, *, no_clear: bool, ai_game: bool) -> GameState:
    if state.winner is not None:
        return state
    if state.actor.money >= ACTION_COST and not state.extra_action_bought:
        command = (
            input(
                f"\nPay ${ACTION_COST:,} to take another action? "
                f"(you have ${state.actor.money:,}) [y/N]: "
            )
            .strip()
            .lower()
        )
        if command == "y":
            return buy_extra_action(state)
    next_state = end_turn(state)
    if not ai_game:
        _handoff(f"Pass the terminal to {next_state.actor.name}.", no_clear=no_clear)
    return next_state


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    first = input("Bird player name [Bird]: ").strip() or "Bird"
    second = "Sea AI" if args.ai else input("Sea player name [Sea]: ").strip() or "Sea"
    ai_knowledge = _load_ai_knowledge(args.ai_cache) if args.ai else None
    state = new_game(
        first,
        BIRD_RULES,
        second,
        SEA_RULES,
        seed=args.seed,
        starting_money=args.starting_money,
    )
    campaign = CampaignState(state)
    while campaign.winner is None:
        state = campaign.round
        while state.winner is None:
            ai_turn = ai_knowledge is not None and state.turn == 1
            if state.phase is TurnPhase.DUAL_SECOND_ANSWER:
                if ai_turn:
                    assert ai_knowledge is not None
                    state, ai_knowledge = _ai_resolve_second(state, ai_knowledge)
                else:
                    state = _resolve_second_answer(state)
                continue
            if state.phase is TurnPhase.POST_ACTION:
                if ai_turn:
                    state = end_turn(state)
                else:
                    state = _post_action(state, no_clear=args.no_clear, ai_game=args.ai)
                continue
            if ai_turn:
                assert ai_knowledge is not None
                state, ai_knowledge = _ai_action(state, ai_knowledge)
                continue
            _handoff(
                f"{state.actor.name}, make sure only you can see the terminal.",
                no_clear=args.no_clear,
            )
            _show_private_turn(state, ai_knowledge)
            command = input("\n[a]sk, a[c]cuse, [q]uit: ").strip().lower()
            try:
                if command == "a":
                    state = _ask(state, no_clear=args.no_clear, ai_opponent=args.ai)
                elif command == "c":
                    state = _accuse(state)
                elif command == "q":
                    return
            except (ValueError, IndexError) as error:
                print(error)
                input("Press Enter to continue...")
        round_winner = state.players[state.winner]
        print(
            f"\n{round_winner.name} wins round {campaign.round_number}. "
            f"Money: {state.players[0].name} ${state.players[0].money:,}, "
            f"{state.players[1].name} ${state.players[1].money:,}"
        )
        campaign = next_campaign_round(replace(campaign, round=state))
        if campaign.winner is None:
            if ai_knowledge is not None:
                ai_knowledge = reset_ai_knowledge(ai_knowledge)
            input("\nPress Enter to begin the next round...")
    winner = campaign.round.players[campaign.winner]
    print(f"\n{winner.name} wins the campaign with ${winner.money:,}!")


def main() -> None:
    run()
