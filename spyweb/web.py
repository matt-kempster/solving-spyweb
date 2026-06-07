from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import cast

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
    Accusation,
    AskedQuestion,
    BoughtExtraAction,
    BoughtSecondAnswer,
    CampaignState,
    EndedTurn,
    GameEvent,
    GameState,
    TurnPhase,
    accuse,
    ask_question,
    buy_extra_action,
    buy_second_answer,
    decline_second_answer,
    end_turn,
    legal_questions,
    new_campaign,
    next_campaign_round,
)
from spyweb.core.model import (
    Answer,
    CityId,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Rules,
    Sense,
    SpyAnswer,
    SpyId,
)
from spyweb.core.rules import answer_question
from spyweb.solver.belief import pair_count

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

STATIC_DIR = Path(__file__).with_name("web_static")


def _answer_label(rules: Rules, answer: Answer) -> str:
    if isinstance(answer, NothingAnswer):
        return "Nothing"
    if isinstance(answer, SpyAnswer):
        return rules.spies[int(answer.spy)].name
    if isinstance(answer, LandmarkAnswer):
        return rules.landmarks[int(answer.landmark)].name
    raise TypeError(answer)


def _event_record(state: GameState, event: GameEvent) -> dict[str, JsonValue]:
    if isinstance(event, AskedQuestion):
        rules = state.players[1 - event.asker].rules
        spy = rules.spies[int(event.question.spy)].name
        return {
            "player": event.asker,
            "text": f"{spy} {event.question.sense.name.lower()} -> "
            f"{_answer_label(rules, event.answer)}",
            "kind": "observation",
        }
    if isinstance(event, BoughtSecondAnswer):
        rules = state.players[1 - event.asker].rules
        spy = rules.spies[int(event.question.spy)].name
        return {
            "player": event.asker,
            "text": f"{spy} second direction -> {_answer_label(rules, event.answer)}",
            "kind": "observation",
        }
    if isinstance(event, Accusation):
        rules = state.players[1 - event.accuser].rules
        spy = rules.spies[int(event.ringleader)].name
        city = rules.cities[int(event.hideout)].name
        result = "correct" if event.correct else "wrong"
        return {
            "player": event.accuser,
            "text": f"Accused {spy} in {city}: {result}",
            "kind": "accusation",
        }
    if isinstance(event, BoughtExtraAction):
        return {
            "player": event.actor,
            "text": "Paid $100,000 for another action",
            "kind": "payment",
        }
    if isinstance(event, EndedTurn):
        return {"player": event.actor, "text": "Ended turn", "kind": "turn"}
    raise TypeError(event)


def _player_record(state: GameState, player_index: int, *, private: bool) -> dict[str, JsonValue]:
    player = state.players[player_index]
    record: dict[str, JsonValue] = {
        "id": player_index,
        "name": player.name,
        "faction": player.rules.spies[0].faction.value,
        "money": player.money,
    }
    if not private:
        return record
    record["ringleader"] = player.rules.spies[int(player.board.ringleader)].name
    record["hideout"] = player.rules.cities[int(player.board.hideout)].name
    occupants = player.board.occupant_by_city
    record["board"] = [
        {
            "id": int(city.id),
            "city": city.name,
            "occupant": (
                "HIDEOUT"
                if occupants[int(city.id)] is None
                else player.rules.spies[int(cast(SpyId, occupants[int(city.id)]))].name
            ),
        }
        for city in player.rules.cities
    ]
    return record


def _cards_record(rules: Rules) -> list[JsonValue]:
    return [
        {
            "id": int(spy.id),
            "name": spy.name,
            "bounty": spy.bounty,
            "look": [direction.name for direction in spy.directions[Sense.LOOK]],
            "hear": [direction.name for direction in spy.directions[Sense.HEAR]],
            "point": [direction.name for direction in spy.directions[Sense.POINT]],
        }
        for spy in rules.spies
    ]


def project_campaign(
    campaign: CampaignState,
    viewer: int,
    *,
    ai_knowledge: AiKnowledge | None = None,
    ai_pending_question: Question | None = None,
) -> dict[str, JsonValue]:
    if viewer not in (0, 1):
        raise ValueError("Viewer must be player 0 or 1")
    if ai_knowledge is not None and viewer != 0:
        raise ValueError("The AI's private board is not viewable")
    state = campaign.round
    opponent = 1 - viewer
    questions = legal_questions(state.players[opponent].rules)
    history = [_event_record(state, event) for event in state.history]
    return {
        "round": campaign.round_number,
        "campaignWinner": campaign.winner,
        "winner": state.winner,
        "turn": state.turn,
        "phase": state.phase.value,
        "extraActionBought": state.extra_action_bought,
        "aiEnabled": ai_knowledge is not None,
        "aiThinking": ai_knowledge is not None and state.turn == 1 and ai_pending_question is None,
        "aiBelief": (
            None
            if ai_knowledge is None
            else {
                "boards": int(ai_knowledge.belief.size),
                "pairs": pair_count(ai_knowledge.universe, ai_knowledge.belief),
            }
        ),
        "aiQuestion": (
            None
            if ai_pending_question is None
            else {
                "spy": state.players[0].rules.spies[int(ai_pending_question.spy)].name,
                "sense": ai_pending_question.sense.name.lower(),
                "answers": [
                    _answer_label(state.players[0].rules, answer)
                    for answer in answer_question(
                        state.players[0].rules,
                        state.players[0].board,
                        ai_pending_question,
                    )
                ],
            }
        ),
        "viewer": viewer,
        "players": [
            _player_record(state, 0, private=viewer == 0),
            _player_record(state, 1, private=viewer == 1),
        ],
        "ownCards": _cards_record(state.players[viewer].rules),
        "opponentCards": _cards_record(state.players[opponent].rules),
        "cities": [
            {"id": int(city.id), "name": city.name} for city in state.players[viewer].rules.cities
        ],
        "landmarks": [
            {"id": int(landmark.id), "name": landmark.name}
            for landmark in state.players[viewer].rules.landmarks
        ],
        "questions": [
            {
                "spy": int(question.spy),
                "spyName": state.players[opponent].rules.spies[int(question.spy)].name,
                "sense": question.sense.name.lower(),
                "dual": len(
                    state.players[opponent]
                    .rules.spies[int(question.spy)]
                    .directions[question.sense]
                )
                == 2,
            }
            for question in questions
        ],
        "history": cast(list[JsonValue], history),
        "knowledge": [
            [
                event["text"]
                for event in history
                if event["player"] == player and event["kind"] in ("observation", "accusation")
            ]
            for player in (0, 1)
        ],
    }


@dataclass
class WebSession:
    campaign: CampaignState
    seed: int | None = None
    ai_knowledge: AiKnowledge | None = None
    ai_pending_question: Question | None = None

    def project(self, viewer: int) -> dict[str, JsonValue]:
        return project_campaign(
            self.campaign,
            viewer,
            ai_knowledge=self.ai_knowledge,
            ai_pending_question=self.ai_pending_question,
        )

    def apply(self, action: dict[str, JsonValue]) -> None:
        kind = _string(action, "type")
        player = _integer(action, "player")
        state = self.campaign.round
        if kind == "ai_answer":
            self._apply_ai_answer(player, _integer(action, "firstAnswerIndex"))
            self.advance_ai()
            return
        if kind == "next_round":
            if self.ai_knowledge is not None and player != 0:
                raise ValueError("Only the human player can start the next round")
            self.campaign = next_campaign_round(self.campaign, seed=self.seed)
            if self.ai_knowledge is not None:
                self.ai_knowledge = reset_ai_knowledge(self.ai_knowledge)
            self.advance_ai()
            return
        if player != state.turn:
            raise ValueError("It is not that player's turn")
        if self.ai_knowledge is not None and player == 1:
            raise ValueError("The AI controls Sea")
        if kind == "ask":
            question = Question(
                SpyId(_integer(action, "spy")),
                Sense[_string(action, "sense").upper()],
            )
            index = _integer(action, "firstAnswerIndex", default=0)
            state = ask_question(state, question, first_answer_index=index)
        elif kind == "buy_second":
            state = buy_second_answer(state)
        elif kind == "decline_second":
            state = decline_second_answer(state)
        elif kind == "buy_extra":
            state = buy_extra_action(state)
        elif kind == "end_turn":
            state = end_turn(state)
        elif kind == "accuse":
            state = accuse(
                state,
                SpyId(_integer(action, "ringleader")),
                CityId(_integer(action, "hideout")),
            )
        else:
            raise ValueError(f"Unknown action: {kind}")
        self.campaign = CampaignState(state, self.campaign.round_number, self.campaign.winner)
        self.advance_ai()

    def _apply_ai_answer(self, player: int, first_answer_index: int) -> None:
        if player != 0 or self.ai_knowledge is None or self.ai_pending_question is None:
            raise ValueError("There is no AI question awaiting your answer")
        state = self.campaign.round
        question = self.ai_pending_question
        answers = answer_question(state.opponent.rules, state.opponent.board, question)
        if first_answer_index not in (0, 1):
            raise ValueError("Choose one of the two truthful answers")
        first = answers[first_answer_index]
        state = ask_question(state, question, first_answer_index=first_answer_index)
        self.ai_knowledge = observe_first(self.ai_knowledge, question, first)
        self.ai_pending_question = None
        self.campaign = CampaignState(state, self.campaign.round_number, self.campaign.winner)

    def advance_ai(self) -> None:
        while self.ai_knowledge is not None:
            state = self.campaign.round
            if state.winner is not None or state.turn != 1 or self.ai_pending_question is not None:
                return
            if state.phase is TurnPhase.ACTION:
                candidate = accusation_candidate(self.ai_knowledge)
                if candidate is not None:
                    state = accuse(
                        state,
                        BIRD_RULES.spies[candidate.ringleader].id,
                        BIRD_RULES.cities[candidate.hideout].id,
                    )
                else:
                    question = recommended_question(self.ai_knowledge)
                    answers = answer_question(BIRD_RULES, state.opponent.board, question)
                    if len(answers) == 2:
                        self.ai_pending_question = question
                        return
                    state = ask_question(state, question)
                    self.ai_knowledge = observe_first(self.ai_knowledge, question, answers[0])
            elif state.phase is TurnPhase.DUAL_SECOND_ANSWER:
                pending = state.pending_second
                event = state.history[-1]
                if pending is None or not isinstance(event, AskedQuestion):
                    raise RuntimeError("Invalid AI second-answer state")
                if state.actor.money >= ACTION_COST and should_buy_second(
                    self.ai_knowledge, pending.question, event.answer
                ):
                    state = buy_second_answer(state)
                    second = state.history[-1]
                    if not isinstance(second, BoughtSecondAnswer):
                        raise RuntimeError("Missing AI second-answer event")
                    self.ai_knowledge = observe_second(
                        self.ai_knowledge,
                        pending.question,
                        event.answer,
                        second.answer,
                    )
                else:
                    state = decline_second_answer(state)
            else:
                state = end_turn(state)
            self.campaign = CampaignState(state, self.campaign.round_number, self.campaign.winner)


def _string(record: dict[str, JsonValue], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _integer(record: dict[str, JsonValue], key: str, *, default: int | None = None) -> int:
    value = record.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


_SESSION: WebSession | None = None
_LOCK = Lock()


def _session() -> WebSession:
    if _SESSION is None:
        raise RuntimeError("Web session has not been initialized")
    return _SESSION


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        try:
            if self.path.startswith("/api/state"):
                query = self.path.partition("?")[2]
                viewer = int(
                    next(
                        (part[7:] for part in query.split("&") if part.startswith("viewer=")),
                        "0",
                    )
                )
                with _LOCK:
                    self._json(_session().project(viewer))
                return
            filename = "index.html" if self.path == "/" else self.path.lstrip("/")
            path = STATIC_DIR / filename
            if path.parent != STATIC_DIR or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = {
                ".html": "text/html",
                ".css": "text/css",
                ".js": "text/javascript",
            }.get(path.suffix, "application/octet-stream")
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (KeyError, ValueError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        if self.path != "/api/action":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            raw = json.loads(self.rfile.read(size))
            if not isinstance(raw, dict):
                raise ValueError("Action must be an object")
            action = cast(dict[str, JsonValue], raw)
            viewer = _integer(action, "player")
            with _LOCK:
                _session().apply(action)
                response = _session().project(viewer)
            self._json(response)
        except (KeyError, ValueError, json.JSONDecodeError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, value: JsonValue, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Spy Web browser UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--ai", action="store_true", help="play Bird against the Sea AI")
    parser.add_argument(
        "--ai-cache",
        type=Path,
        default=Path(".cache/play-ai-bird.npz"),
        help="cache for the AI's exact Bird-board universe",
    )
    args = parser.parse_args(argv)
    global _SESSION
    ai_knowledge = None
    if args.ai:
        print(f"Loading or building AI knowledge at {args.ai_cache}...")
        ai_knowledge = load_ai_knowledge(BIRD_RULES, args.ai_cache)
    _SESSION = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI" if args.ai else "Sea", SEA_RULES, seed=args.seed),
        args.seed,
        ai_knowledge,
    )
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Spy Web web UI: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
