from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from spyweb.core.model import (
    City,
    CityId,
    Coord,
    Direction,
    Directions,
    Faction,
    Landmark,
    LandmarkId,
    Rules,
    Sense,
    Spy,
    SpyId,
)
from spyweb.core.rules import validate_rules

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
RULES_FORMAT_VERSION = 1


def _rules_record(rules: Rules) -> dict[str, JsonValue]:
    return {
        "format": "spyweb-rules",
        "version": RULES_FORMAT_VERSION,
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


def write_rules(rules: Rules, path: Path) -> None:
    validate_rules(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(_rules_record(rules), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _record(value: JsonValue, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object")
    return value


def _array(value: JsonValue, context: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return value


def _string(record: dict[str, JsonValue], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{context}.{key} must be a string")
    return value


def _integer(record: dict[str, JsonValue], key: str, context: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def _coord(value: JsonValue, context: str) -> Coord:
    values = _array(value, context)
    if (
        len(values) != 2
        or not isinstance(values[0], int)
        or isinstance(values[0], bool)
        or not isinstance(values[1], int)
        or isinstance(values[1], bool)
    ):
        raise ValueError(f"{context} must contain exactly two integers")
    return Coord(values[0], values[1])


def _directions(value: JsonValue, context: str) -> Directions:
    names = _array(value, context)
    if len(names) not in (1, 2) or not all(isinstance(name, str) for name in names):
        raise ValueError(f"{context} must contain one or two direction names")
    try:
        parsed = tuple(Direction[cast(str, name).upper()] for name in names)
    except KeyError as error:
        raise ValueError(f"{context} contains an unknown direction") from error
    return cast(Directions, parsed)


def _spy(value: JsonValue, index: int) -> Spy:
    context = f"spies[{index}]"
    record = _record(value, context)
    try:
        faction = Faction(_string(record, "faction", context))
    except ValueError as error:
        raise ValueError(f"{context}.faction is unknown") from error
    directions_record = _record(record.get("directions"), f"{context}.directions")
    directions = {
        sense: _directions(
            directions_record.get(sense.name.lower()),
            f"{context}.directions.{sense.name.lower()}",
        )
        for sense in Sense
    }
    return Spy(
        SpyId(_integer(record, "id", context)),
        _string(record, "name", context),
        faction,
        _integer(record, "bounty", context),
        directions,
    )


def _city(value: JsonValue, index: int) -> City:
    context = f"cities[{index}]"
    record = _record(value, context)
    return City(
        CityId(_integer(record, "id", context)),
        _string(record, "name", context),
        _coord(record.get("coord"), f"{context}.coord"),
    )


def _landmark(value: JsonValue, index: int) -> Landmark:
    context = f"landmarks[{index}]"
    record = _record(value, context)
    return Landmark(
        LandmarkId(_integer(record, "id", context)),
        _string(record, "name", context),
        _coord(record.get("coord"), f"{context}.coord"),
    )


def read_rules(path: Path) -> Rules:
    value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    record = _record(value, "rules")
    if record.get("format") != "spyweb-rules":
        raise ValueError("Not a Spy Web rules file")
    if record.get("version") != RULES_FORMAT_VERSION:
        raise ValueError(f"Unsupported rules version: {record.get('version')}")
    spy_values = _array(record.get("spies"), "spies")
    city_values = _array(record.get("cities"), "cities")
    landmark_values = _array(record.get("landmarks"), "landmarks")
    rules = Rules(
        tuple(_spy(value, index) for index, value in enumerate(spy_values)),
        tuple(_city(value, index) for index, value in enumerate(city_values)),
        tuple(
            _landmark(value, index)
            for index, value in enumerate(landmark_values)
        ),
    )
    validate_rules(rules)
    return rules
