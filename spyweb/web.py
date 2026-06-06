from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import cast

from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    Accusation,
    AskedQuestion,
    BoughtExtraAction,
    BoughtSecondAnswer,
    CampaignState,
    EndedTurn,
    GameEvent,
    GameState,
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


def project_campaign(campaign: CampaignState, viewer: int) -> dict[str, JsonValue]:
    if viewer not in (0, 1):
        raise ValueError("Viewer must be player 0 or 1")
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
        "viewer": viewer,
        "players": [
            _player_record(state, 0, private=viewer == 0),
            _player_record(state, 1, private=viewer == 1),
        ],
        "opponentCards": _cards_record(state.players[opponent].rules),
        "cities": [
            {"id": int(city.id), "name": city.name} for city in state.players[viewer].rules.cities
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

    def apply(self, action: dict[str, JsonValue]) -> None:
        kind = _string(action, "type")
        player = _integer(action, "player")
        state = self.campaign.round
        if player != state.turn:
            raise ValueError("It is not that player's turn")
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
        elif kind == "next_round":
            self.campaign = next_campaign_round(self.campaign, seed=self.seed)
            return
        else:
            raise ValueError(f"Unknown action: {kind}")
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
                    self._json(project_campaign(_session().campaign, viewer))
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
                response = project_campaign(_session().campaign, viewer)
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
    args = parser.parse_args(argv)
    global _SESSION
    _SESSION = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=args.seed),
        args.seed,
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
