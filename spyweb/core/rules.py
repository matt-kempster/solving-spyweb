import json
from hashlib import sha256

from spyweb.core.model import (
    DIRECTION_DELTA,
    Answer,
    Board,
    Coord,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    QuestionAnswers,
    Rules,
    Sense,
    SpyAnswer,
    SpyId,
)


def rules_fingerprint(rules: Rules) -> str:
    record = {
        "spies": [
            {
                "id": int(spy.id),
                "name": spy.name,
                "faction": spy.faction.value,
                "bounty": spy.bounty,
                "directions": {
                    sense.name.lower(): [direction.name for direction in spy.directions[sense]]
                    for sense in Sense
                },
            }
            for spy in rules.spies
        ],
        "cities": [
            {
                "id": int(city.id),
                "name": city.name,
                "coord": [city.coord.row, city.coord.col],
            }
            for city in rules.cities
        ],
        "landmarks": [
            {
                "id": int(landmark.id),
                "name": landmark.name,
                "coord": [landmark.coord.row, landmark.coord.col],
            }
            for landmark in rules.landmarks
        ],
    }
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def validate_rules(rules: Rules) -> None:
    if len(rules.spies) != len(rules.cities):
        raise ValueError("Spy Web requires the same number of spies and cities")
    if [int(spy.id) for spy in rules.spies] != list(range(len(rules.spies))):
        raise ValueError("Spy ids must be dense and ordered")
    if [int(city.id) for city in rules.cities] != list(range(len(rules.cities))):
        raise ValueError("City ids must be dense and ordered")
    for spy in rules.spies:
        if set(spy.directions) != set(Sense):
            raise ValueError(f"{spy.name} must specify every sense, including unavailable ones")
        if any(len(directions) > 2 for directions in spy.directions.values()):
            raise ValueError(f"{spy.name} senses may have at most two directions")


def validate_board(rules: Rules, board: Board) -> None:
    validate_rules(rules)
    if len(board.occupant_by_city) != len(rules.cities):
        raise ValueError("Board must have exactly one slot per city")
    if board.occupant_by_city[int(board.hideout)] is not None:
        raise ValueError("Hideout city must be empty")
    occupants: list[SpyId] = [spy for spy in board.occupant_by_city if spy is not None]
    if len(occupants) != len(rules.spies) - 1:
        raise ValueError("Board must contain every non-ringleader spy")
    if board.ringleader in occupants:
        raise ValueError("Ringleader must not be on the board")
    if len(set(occupants)) != len(occupants):
        raise ValueError("A spy may only occupy one city")


def _answer_direction(
    rules: Rules, board: Board, question: Question, direction_index: int
) -> Answer:
    if question.spy == board.ringleader:
        return NothingAnswer()
    city_index = board.occupant_by_city.index(question.spy)
    start = rules.cities[city_index].coord
    direction = rules.spies[int(question.spy)].directions[question.sense][direction_index]
    dr, dc = DIRECTION_DELTA[direction]
    target = Coord(start.row + dr, start.col + dc)
    landmark = next((item for item in rules.landmarks if item.coord == target), None)
    if landmark is not None:
        return LandmarkAnswer(landmark.id)
    city = next((item for item in rules.cities if item.coord == target), None)
    if city is None:
        return NothingAnswer()
    occupant: SpyId | None = board.occupant_by_city[int(city.id)]
    return NothingAnswer() if occupant is None else SpyAnswer(occupant)


def answer_question(rules: Rules, board: Board, question: Question) -> QuestionAnswers:
    directions = rules.spies[int(question.spy)].directions[question.sense]
    if not directions:
        raise ValueError(
            f"{rules.spies[int(question.spy)].name} cannot {question.sense.name.lower()}"
        )
    first = _answer_direction(rules, board, question, 0)
    if len(directions) == 1:
        return (first,)
    return (first, _answer_direction(rules, board, question, 1))
