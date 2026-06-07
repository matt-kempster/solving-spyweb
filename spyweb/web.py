from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from random import Random
from threading import Lock
from typing import cast

from spyweb.ai import (
    AiKnowledge,
    ai_search_depth,
    choose_defensive_board,
    load_ai_knowledge,
    observe_accusation,
    observe_first,
    observe_second,
    recommended_action,
    reset_ai_knowledge,
    should_buy_extra_for_accusation,
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
    Board,
    CityId,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Rules,
    Sense,
    SpyAnswer,
    SpyId,
)
from spyweb.core.rules import answer_question, validate_board
from spyweb.solver.belief import PairCandidate, pair_count

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
            "faction": spy.faction.value,
            "bounty": spy.bounty,
            "look": [direction.name for direction in spy.directions[Sense.LOOK]],
            "hear": [direction.name for direction in spy.directions[Sense.HEAR]],
            "point": [direction.name for direction in spy.directions[Sense.POINT]],
        }
        for spy in rules.spies
    ]


def _deduction_record(state: GameState, player_index: int) -> dict[str, JsonValue]:
    target = 1 - player_index
    rules = state.players[target].rules
    asked_counts: dict[tuple[int, Sense], int] = {}
    edges: list[JsonValue] = []
    anchors: list[JsonValue] = []
    nothings: list[JsonValue] = []
    accusations: list[JsonValue] = []

    def directions(question: Question) -> list[str]:
        return [
            direction.name
            for direction in rules.spies[int(question.spy)].directions[question.sense]
        ]

    def spy_name(spy: SpyId) -> str:
        return rules.spies[int(spy)].name

    def city_name(city: CityId) -> str:
        return rules.cities[int(city)].name

    def observe(question: Question, answer: Answer) -> None:
        key = (int(question.spy), question.sense)
        asked_counts[key] = asked_counts.get(key, 0) + 1
        base: dict[str, JsonValue] = {
            "spy": spy_name(question.spy),
            "sense": question.sense.name.lower(),
            "directions": cast(list[JsonValue], directions(question)),
        }
        if isinstance(answer, SpyAnswer):
            edges.append({**base, "target": spy_name(answer.spy)})
        elif isinstance(answer, LandmarkAnswer):
            anchors.append({**base, "target": rules.landmarks[int(answer.landmark)].name})
        elif isinstance(answer, NothingAnswer):
            nothings.append(base)
        else:
            raise TypeError(answer)

    for event in state.history:
        if isinstance(event, (AskedQuestion, BoughtSecondAnswer)) and event.asker == player_index:
            observe(event.question, event.answer)
        elif isinstance(event, Accusation) and event.accuser == player_index:
            accusations.append(
                {
                    "ringleader": spy_name(event.ringleader),
                    "hideout": city_name(event.hideout),
                    "correct": event.correct,
                }
            )

    asked: list[JsonValue] = []
    for spy in rules.spies:
        senses: list[JsonValue] = [
            {
                "sense": sense.name.lower(),
                "available": bool(spy.directions[sense]),
                "count": asked_counts.get((int(spy.id), sense), 0),
            }
            for sense in Sense
        ]
        asked.append({"spy": spy.name, "senses": senses})
    return {
        "player": player_index,
        "targetFaction": rules.spies[0].faction.value,
        "asked": asked,
        "edges": edges,
        "anchors": anchors,
        "nothings": nothings,
        "accusations": accusations,
    }


def project_campaign(
    campaign: CampaignState,
    viewer: int,
    *,
    ai_knowledge: AiKnowledge | None = None,
    ai_pending_question: Question | None = None,
    human_player: int = 0,
    ai_player: int | None = None,
    setup_enabled: bool = False,
    setup_ready: frozenset[int] = frozenset(),
) -> dict[str, JsonValue]:
    if viewer not in (0, 1):
        raise ValueError("Viewer must be player 0 or 1")
    if ai_knowledge is not None and viewer != human_player:
        raise ValueError("The AI's private board is not viewable")
    if ai_knowledge is not None and ai_player is None:
        ai_player = 1 - human_player
    state = campaign.round
    opponent = 1 - viewer
    questions = legal_questions(state.players[opponent].rules)
    history = [_event_record(state, event) for event in state.history]
    human_rules = state.players[human_player].rules
    human_board = state.players[human_player].board
    return {
        "round": campaign.round_number,
        "campaignWinner": campaign.winner,
        "winner": state.winner,
        "turn": state.turn,
        "phase": state.phase.value,
        "extraActionBought": state.extra_action_bought,
        "aiEnabled": ai_knowledge is not None,
        "aiThinking": (
            ai_knowledge is not None and state.turn == ai_player and ai_pending_question is None
        ),
        "humanPlayer": human_player,
        "aiPlayer": ai_player,
        "setupEnabled": setup_enabled,
        "setupReady": [player in setup_ready for player in (0, 1)],
        "setupComplete": not setup_enabled or len(setup_ready) == 2,
        "aiBelief": (
            None
            if ai_knowledge is None
            else {
                "boards": int(ai_knowledge.belief.size),
                "pairs": pair_count(ai_knowledge.universe, ai_knowledge.belief),
                "depth": ai_search_depth(int(ai_knowledge.belief.size)),
            }
        ),
        "aiQuestion": (
            None
            if ai_pending_question is None
            else {
                "spy": human_rules.spies[int(ai_pending_question.spy)].name,
                "sense": ai_pending_question.sense.name.lower(),
                "answers": [
                    _answer_label(human_rules, answer)
                    for answer in answer_question(
                        human_rules,
                        human_board,
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
            {
                "id": int(landmark.id),
                "name": landmark.name,
                "row": landmark.coord.row,
                "col": landmark.coord.col,
            }
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
        "deductions": [_deduction_record(state, player) for player in (0, 1)],
    }


@dataclass
class WebSession:
    campaign: CampaignState
    seed: int | None = None
    ai_knowledge: AiKnowledge | None = None
    human_player: int = 0
    ai_player: int | None = None
    ai_pending_question: Question | None = None
    setup_enabled: bool = False
    setup_ready: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.ai_knowledge is not None and self.ai_player is None:
            self.ai_player = 1 - self.human_player

    def project(self, viewer: int) -> dict[str, JsonValue]:
        return project_campaign(
            self.campaign,
            viewer,
            ai_knowledge=self.ai_knowledge,
            ai_pending_question=self.ai_pending_question,
            human_player=self.human_player,
            ai_player=self.ai_player,
            setup_enabled=self.setup_enabled,
            setup_ready=frozenset(self.setup_ready),
        )

    def prepare_setup(self) -> None:
        if not self.setup_enabled:
            return
        self.setup_ready.clear()
        if self.ai_knowledge is None or self.ai_player is None:
            return
        state = self.campaign.round
        random = Random(None if self.seed is None else self.seed + self.campaign.round_number)
        ai_state = state.players[self.ai_player]
        board = choose_defensive_board(ai_state.rules, ai_state.board.ringleader, random)
        players = list(state.players)
        players[self.ai_player] = replace(ai_state, board=board)
        self.campaign = replace(
            self.campaign,
            round=replace(
                state,
                players=(players[0], players[1]),
            ),
        )
        self.setup_ready.add(self.ai_player)

    def apply(self, action: dict[str, JsonValue]) -> None:
        kind = _string(action, "type")
        player = _integer(action, "player")
        state = self.campaign.round
        if kind == "set_layout":
            self._set_layout(player, action)
            self.advance_ai()
            return
        if kind == "ai_answer":
            self._apply_ai_answer(player, _integer(action, "firstAnswerIndex"))
            self.advance_ai()
            return
        if kind == "next_round":
            if self.ai_knowledge is not None and player != self.human_player:
                raise ValueError("Only the human player can start the next round")
            self.campaign = next_campaign_round(self.campaign, seed=self.seed)
            if self.ai_knowledge is not None:
                self.ai_knowledge = reset_ai_knowledge(self.ai_knowledge)
            self.prepare_setup()
            self.advance_ai()
            return
        if self.setup_enabled and len(self.setup_ready) != 2:
            raise ValueError("Both players must lock their layouts before play")
        if player != state.turn:
            raise ValueError("It is not that player's turn")
        if self.ai_knowledge is not None and player == self.ai_player:
            raise ValueError(f"The AI controls {state.players[player].name}")
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

    def _set_layout(self, player: int, action: dict[str, JsonValue]) -> None:
        if not self.setup_enabled:
            raise ValueError("Layout selection is not enabled")
        if player not in (0, 1):
            raise ValueError("Unknown player")
        state = self.campaign.round
        if self.ai_knowledge is not None and player == self.ai_player:
            raise ValueError(f"The AI controls {state.players[player].name}'s layout")
        if player in self.setup_ready:
            raise ValueError("That layout is already locked")
        raw_occupants = action.get("occupants")
        if not isinstance(raw_occupants, list):
            raise ValueError("occupants must be a list")
        current = state.players[player]
        if len(raw_occupants) != len(current.rules.cities):
            raise ValueError("Layout must contain one occupant per city")
        occupants: list[SpyId | None] = []
        for value in raw_occupants:
            if value == -1:
                occupants.append(None)
            elif isinstance(value, int) and not isinstance(value, bool):
                occupants.append(SpyId(value))
            else:
                raise ValueError("Each layout occupant must be a spy id or -1")
        try:
            hideout = current.rules.cities[occupants.index(None)].id
        except ValueError as error:
            raise ValueError("Layout must contain exactly one hideout") from error
        board = Board(current.board.ringleader, hideout, tuple(occupants))
        validate_board(current.rules, board)
        players = list(state.players)
        players[player] = replace(current, board=board)
        self.campaign = replace(
            self.campaign, round=replace(state, players=(players[0], players[1]))
        )
        self.setup_ready.add(player)

    def _apply_ai_answer(self, player: int, first_answer_index: int) -> None:
        if (
            player != self.human_player
            or self.ai_knowledge is None
            or self.ai_pending_question is None
        ):
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
            if self.ai_player is None:
                raise RuntimeError("AI player is not configured")
            state = self.campaign.round
            if self.setup_enabled and len(self.setup_ready) != 2:
                return
            if (
                state.winner is not None
                or state.turn != self.ai_player
                or self.ai_pending_question is not None
            ):
                return
            target = state.players[self.human_player]
            if state.phase is TurnPhase.ACTION:
                action = recommended_action(self.ai_knowledge)
                if isinstance(action, PairCandidate):
                    state = accuse(
                        state,
                        target.rules.spies[action.ringleader].id,
                        target.rules.cities[action.hideout].id,
                    )
                    event = state.history[-1]
                    if not isinstance(event, Accusation):
                        raise RuntimeError("Missing AI accusation event")
                    self.ai_knowledge = observe_accusation(
                        self.ai_knowledge,
                        event.ringleader,
                        event.hideout,
                        correct=event.correct,
                    )
                else:
                    question = action
                    answers = answer_question(target.rules, target.board, question)
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
                    state, self.ai_knowledge, pending.question, event.answer
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
            elif should_buy_extra_for_accusation(state, self.ai_knowledge):
                state = buy_extra_action(state)
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
_AI_ENABLED = False
_AI_CACHE = Path(".cache/play-ai-bird.npz")
_SEED: int | None = None


def _session() -> WebSession:
    if _SESSION is None:
        raise RuntimeError("Web session has not been initialized")
    return _SESSION


def _cache_for_faction(cache: Path, faction: str) -> Path:
    stem = cache.stem
    for suffix in ("-bird", "-sea"):
        if stem.endswith(suffix):
            stem = stem.removesuffix(suffix)
            break
    return cache.with_name(f"{stem}-{faction}{cache.suffix}")


def _new_web_session(human_faction: str) -> WebSession:
    if human_faction not in ("bird", "sea"):
        raise ValueError("Faction must be bird or sea")
    human_player = 0 if human_faction == "bird" else 1
    ai_player = 1 - human_player if _AI_ENABLED else None
    bird_name = "Bird AI" if ai_player == 0 else "Bird"
    sea_name = "Sea AI" if ai_player == 1 else "Sea"
    knowledge = None
    if _AI_ENABLED:
        human_rules = BIRD_RULES if human_player == 0 else SEA_RULES
        cache = _cache_for_faction(_AI_CACHE, human_faction)
        print(f"Loading or building AI knowledge at {cache}...")
        knowledge = load_ai_knowledge(human_rules, cache)
    session = WebSession(
        new_campaign(bird_name, BIRD_RULES, sea_name, SEA_RULES, seed=_SEED),
        _SEED,
        knowledge,
        human_player=human_player,
        ai_player=ai_player,
        setup_enabled=True,
    )
    session.prepare_setup()
    return session


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
            try:
                path.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = {
                ".html": "text/html",
                ".css": "text/css",
                ".js": "text/javascript",
                ".json": "application/json",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
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
                current = _session()
                if action.get("type") in ("choose_faction", "new_game"):
                    if action.get("type") == "choose_faction" and not _AI_ENABLED:
                        raise ValueError("Faction selection is only available against the AI")
                    global _SESSION
                    if action.get("type") == "choose_faction":
                        faction = _string(action, "faction")
                    else:
                        human = current.campaign.round.players[current.human_player]
                        faction = human.rules.spies[0].faction.value
                    _SESSION = _new_web_session(faction)
                    response = _SESSION.project(_SESSION.human_player)
                else:
                    current.apply(action)
                    response = current.project(viewer)
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
    parser.add_argument("--ai", action="store_true", help="play against the AI")
    parser.add_argument(
        "--ai-cache",
        type=Path,
        default=Path(".cache/play-ai-bird.npz"),
        help="base cache path for the AI's exact faction universes",
    )
    args = parser.parse_args(argv)
    global _AI_CACHE, _AI_ENABLED, _SEED, _SESSION
    _AI_ENABLED = args.ai
    _AI_CACHE = args.ai_cache
    _SEED = args.seed
    _SESSION = _new_web_session("bird")
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
