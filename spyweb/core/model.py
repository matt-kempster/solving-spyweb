from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import NewType

SpyId = NewType("SpyId", int)
CityId = NewType("CityId", int)
LandmarkId = NewType("LandmarkId", int)
QuestionId = NewType("QuestionId", int)
AnswerCode = NewType("AnswerCode", int)


class Faction(StrEnum):
    BIRD = "bird"
    SEA = "sea"


class Sense(IntEnum):
    LOOK = 0
    HEAR = 1
    POINT = 2


class Direction(IntEnum):
    N = 0
    NE = 1
    E = 2
    SE = 3
    S = 4
    SW = 5
    W = 6
    NW = 7


DIRECTION_DELTA: Mapping[Direction, tuple[int, int]] = {
    Direction.N: (-1, 0),
    Direction.NE: (-1, 1),
    Direction.E: (0, 1),
    Direction.SE: (1, 1),
    Direction.S: (1, 0),
    Direction.SW: (1, -1),
    Direction.W: (0, -1),
    Direction.NW: (-1, -1),
}


@dataclass(frozen=True)
class Coord:
    row: int
    col: int


Directions = tuple[()] | tuple[Direction] | tuple[Direction, Direction]


@dataclass(frozen=True)
class Spy:
    id: SpyId
    name: str
    faction: Faction
    bounty: int
    directions: Mapping[Sense, Directions]


@dataclass(frozen=True)
class City:
    id: CityId
    name: str
    coord: Coord


@dataclass(frozen=True)
class Landmark:
    id: LandmarkId
    name: str
    coord: Coord


@dataclass(frozen=True)
class Rules:
    spies: tuple[Spy, ...]
    cities: tuple[City, ...]
    landmarks: tuple[Landmark, ...]


@dataclass(frozen=True)
class Board:
    ringleader: SpyId
    hideout: CityId
    occupant_by_city: tuple[SpyId | None, ...]


@dataclass(frozen=True)
class Question:
    spy: SpyId
    sense: Sense


@dataclass(frozen=True)
class SpyAnswer:
    spy: SpyId


@dataclass(frozen=True)
class LandmarkAnswer:
    landmark: LandmarkId


@dataclass(frozen=True)
class NothingAnswer:
    pass


Answer = SpyAnswer | LandmarkAnswer | NothingAnswer
QuestionAnswers = tuple[Answer] | tuple[Answer, Answer]
