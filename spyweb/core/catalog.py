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

CITIES: tuple[City, ...] = tuple(
    City(CityId(index), name, Coord(row, col))
    for index, (name, row, col) in enumerate(
        (
            ("Montreal", 0, 0),
            ("London", 0, 1),
            ("Moscow", 0, 2),
            ("Washington", 1, 0),
            ("Cairo", 1, 1),
            ("Hong Kong", 1, 2),
            ("Rio de Janeiro", 2, 0),
            ("Cape Town", 2, 1),
            ("Melbourne", 2, 2),
        )
    )
)

LANDMARKS: tuple[Landmark, ...] = (
    Landmark(LandmarkId(0), "Car", Coord(0, -1)),
    Landmark(LandmarkId(1), "Plane", Coord(-1, 2)),
    Landmark(LandmarkId(2), "Boat", Coord(2, 3)),
)

type CardData = tuple[
    str,
    int,
    Directions,
    Directions,
    Directions,
]

# Transcribed from the supplied raw card data. An empty tuple means the spy lacks
# that sense; Raven and Urchin have two point directions.
_BIRD_DATA: tuple[CardData, ...] = (
    ("Raven", 300_000, (Direction.W,), (), (Direction.N, Direction.S)),
    ("Buzzard", 300_000, (), (), (Direction.N,)),
    ("Hawk", 100_000, (Direction.W,), (), (Direction.S,)),
    ("Vulture", 300_000, (Direction.W,), (Direction.E,), (Direction.N,)),
    ("Osprey", 200_000, (Direction.E,), (Direction.W,), (Direction.S,)),
    ("Eagle", 400_000, (Direction.E,), (), ()),
    ("Condor", 500_000, (Direction.E,), (), (Direction.W,)),
    ("Falcon", 400_000, (), (Direction.W,), (Direction.S,)),
    ("Crow", 300_000, (Direction.W,), (Direction.E,), (Direction.S,)),
)

_SEA_DATA: tuple[CardData, ...] = (
    ("Stingray", 500_000, (Direction.E,), (Direction.W,), (Direction.N,)),
    ("Urchin", 200_000, (Direction.N,), (), (Direction.E, Direction.W)),
    ("Marlin", 100_000, (Direction.E,), (), (Direction.N,)),
    ("Piranha", 300_000, (Direction.W,), (Direction.E,), (Direction.S,)),
    ("Orca", 300_000, (Direction.W,), (), (Direction.S,)),
    ("Eel", 400_000, (), (), (Direction.S,)),
    ("Shark", 300_000, (Direction.W,), (Direction.E,), (Direction.N,)),
    ("Beluga", 300_000, (Direction.W,), (), ()),
    ("Leech", 400_000, (), (Direction.W,), (Direction.N,)),
)


def _spies(faction: Faction, data: tuple[CardData, ...]) -> tuple[Spy, ...]:
    return tuple(
        Spy(
            SpyId(index),
            name,
            faction,
            bounty,
            {
                Sense.LOOK: look,
                Sense.HEAR: hear,
                Sense.POINT: point,
            },
        )
        for index, (name, bounty, look, hear, point) in enumerate(data)
    )


BIRD_RULES = Rules(_spies(Faction.BIRD, _BIRD_DATA), CITIES, LANDMARKS)
SEA_RULES = Rules(_spies(Faction.SEA, _SEA_DATA), CITIES, LANDMARKS)

# Compatibility alias while callers migrate to selecting a faction explicitly.
FIXTURE_RULES = BIRD_RULES
