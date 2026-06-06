from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from hashlib import sha256
from itertools import permutations
from math import factorial
from pathlib import Path

import numpy as np
import numpy.typing as npt

from spyweb.core.model import (
    DIRECTION_DELTA,
    Board,
    CityId,
    Direction,
    QuestionId,
    Rules,
    Sense,
    SpyId,
)
from spyweb.solver.encoding import Encoding

UInt8Array = npt.NDArray[np.uint8]
Int8Array = npt.NDArray[np.int8]
EMPTY = np.uint8(255)
CACHE_FORMAT_VERSION = 1


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


@dataclass(frozen=True)
class Universe:
    rules_fingerprint: str
    ringleader: UInt8Array
    hideout: UInt8Array
    occupant_by_city: UInt8Array
    answer0: UInt8Array
    answer1: UInt8Array
    dual_question: UInt8Array

    @property
    def board_count(self) -> int:
        return int(self.ringleader.size)

    @property
    def city_count(self) -> int:
        return int(self.occupant_by_city.shape[1])

    def board(self, index: int) -> Board:
        if index < 0 or index >= self.board_count:
            raise IndexError(f"Board index out of range: {index}")
        occupants = tuple(
            None if occupant == EMPTY else SpyId(int(occupant))
            for occupant in self.occupant_by_city[index]
        )
        return Board(
            SpyId(int(self.ringleader[index])),
            CityId(int(self.hideout[index])),
            occupants,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            cache_format_version=np.asarray(CACHE_FORMAT_VERSION),
            rules_fingerprint=np.asarray(self.rules_fingerprint),
            ringleader=self.ringleader,
            hideout=self.hideout,
            occupant_by_city=self.occupant_by_city,
            answer0=self.answer0,
            answer1=self.answer1,
            dual_question=self.dual_question,
        )

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_rules_fingerprint: str | None = None,
        expected_board_count: int | None = None,
    ) -> Universe:
        with np.load(path) as data:
            version = int(data["cache_format_version"])
            if version != CACHE_FORMAT_VERSION:
                raise ValueError(
                    f"Unsupported universe cache version {version}; expected {CACHE_FORMAT_VERSION}"
                )
            fingerprint = str(data["rules_fingerprint"])
            if expected_rules_fingerprint is not None and fingerprint != expected_rules_fingerprint:
                raise ValueError("Universe cache was built from different rules")
            universe = cls(
                fingerprint,
                np.asarray(data["ringleader"], dtype=np.uint8),
                np.asarray(data["hideout"], dtype=np.uint8),
                np.asarray(data["occupant_by_city"], dtype=np.uint8),
                np.asarray(data["answer0"], dtype=np.uint8),
                np.asarray(data["answer1"], dtype=np.uint8),
                np.asarray(data["dual_question"], dtype=np.uint8),
            )
            if expected_board_count is not None and universe.board_count != expected_board_count:
                raise ValueError(
                    f"Universe cache contains {universe.board_count:,} boards; "
                    f"expected {expected_board_count:,}"
                )
            return universe


def _placement_orders(spy_count: int) -> Iterator[tuple[int, ...]]:
    return permutations(range(spy_count - 1))


def universe_board_count(rules: Rules, limit: int | None = None) -> int:
    full_count = len(rules.spies) * len(rules.cities) * factorial(len(rules.spies) - 1)
    return full_count if limit is None else min(limit, full_count)


def build_universe(rules: Rules, encoding: Encoding, limit: int | None = None) -> Universe:
    spy_count = len(rules.spies)
    city_count = len(rules.cities)
    board_count = universe_board_count(rules, limit)
    occupant = np.full((board_count, city_count), EMPTY, dtype=np.uint8)
    ringleader = np.empty(board_count, dtype=np.uint8)
    hideout_array = np.empty(board_count, dtype=np.uint8)
    cursor = 0
    pair_count = spy_count * city_count
    leader_block = np.repeat(np.arange(spy_count, dtype=np.uint8), city_count)
    hideout_block = np.tile(np.arange(city_count, dtype=np.uint8), spy_count)

    for order_indexes in _placement_orders(spy_count):
        remaining = board_count - cursor
        if remaining <= 0:
            break
        block_size = min(pair_count, remaining)
        block = np.full((pair_count, city_count), EMPTY, dtype=np.uint8)
        for leader in range(spy_count):
            visible = [spy for spy in range(spy_count) if spy != leader]
            order = [visible[index] for index in order_indexes]
            leader_rows = block[leader * city_count : (leader + 1) * city_count]
            leader_rows[leader_rows != EMPTY] = EMPTY
            occupied_mask = ~np.eye(city_count, dtype=bool)
            leader_rows[occupied_mask] = np.tile(order, city_count)
        occupant[cursor : cursor + block_size] = block[:block_size]
        ringleader[cursor : cursor + block_size] = leader_block[:block_size]
        hideout_array[cursor : cursor + block_size] = hideout_block[:block_size]
        cursor += block_size

    answer0 = np.empty((encoding.question_count, board_count), dtype=np.uint8)
    answer1 = np.empty_like(answer0)
    dual = np.zeros(encoding.question_count, dtype=np.uint8)

    coords = np.asarray([(city.coord.row, city.coord.col) for city in rules.cities], dtype=np.int8)
    landmark_by_coord = {
        (landmark.coord.row, landmark.coord.col): int(landmark.id) for landmark in rules.landmarks
    }
    locations = np.full((board_count, spy_count), EMPTY, dtype=np.uint8)
    board_ids = np.arange(board_count)
    for city in range(city_count):
        spies = occupant[:, city]
        visible = spies != EMPTY
        locations[board_ids[visible], spies[visible]] = city

    for q in range(encoding.question_count):
        question = encoding.decode_question(QuestionId(q))
        directions = rules.spies[int(question.spy)].directions[question.sense]
        for direction_index, direction in enumerate((directions[0], directions[-1])):
            answers = _answers_for_direction(
                locations,
                occupant,
                coords,
                landmark_by_coord,
                int(question.spy),
                direction,
                encoding,
            )
            (answer0 if direction_index == 0 else answer1)[q] = answers
        dual[q] = len(directions) == 2
    return Universe(
        rules_fingerprint(rules),
        ringleader,
        hideout_array,
        occupant,
        answer0,
        answer1,
        dual,
    )


def _answers_for_direction(
    locations: UInt8Array,
    occupant: UInt8Array,
    coords: Int8Array,
    landmark_by_coord: dict[tuple[int, int], int],
    spy: int,
    direction: Direction,
    encoding: Encoding,
) -> UInt8Array:
    answers = np.full(locations.shape[0], encoding.nothing, dtype=np.uint8)
    visible = locations[:, spy] != EMPTY
    ids = np.flatnonzero(visible)
    starts = coords[locations[ids, spy]]
    target = starts + np.asarray(DIRECTION_DELTA[direction], dtype=np.int8)
    for coord, landmark in landmark_by_coord.items():
        mask = np.all(target == coord, axis=1)
        answers[ids[mask]] = len(encoding.rules.spies) + landmark
    in_board = np.all((target >= 0) & (target < 3), axis=1)
    in_ids = ids[in_board]
    target_city = target[in_board, 0] * 3 + target[in_board, 1]
    target_occupant = occupant[in_ids, target_city]
    answers[in_ids] = np.where(target_occupant == EMPTY, encoding.nothing, target_occupant)
    return answers
