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

# Development fixture only. This is not a verified physical-card transcription.
_FIXTURE_DATA: tuple[tuple[str, int, Directions, Directions, Directions], ...] = (
    ("Raven", 300_000, (Direction.W,), (Direction.E,), (Direction.N, Direction.S)),
    ("Buzzard", 300_000, (Direction.E,), (Direction.W,), (Direction.N,)),
    ("Hawk", 100_000, (Direction.W,), (Direction.E,), (Direction.S,)),
    ("Vulture", 300_000, (Direction.W,), (Direction.E,), (Direction.N,)),
    ("Osprey", 200_000, (Direction.E,), (Direction.W,), (Direction.S,)),
    ("Eagle", 400_000, (Direction.E,), (Direction.W,), (Direction.NW,)),
    ("Condor", 500_000, (Direction.E,), (Direction.N,), (Direction.W,)),
    ("Falcon", 400_000, (Direction.N,), (Direction.W,), (Direction.S,)),
    ("Crow", 300_000, (Direction.W,), (Direction.E,), (Direction.S,)),
)

FIXTURE_SPIES: tuple[Spy, ...] = tuple(
    Spy(
        SpyId(index),
        name,
        Faction.BIRD,
        bounty,
        {
            Sense.LOOK: look,
            Sense.HEAR: hear,
            Sense.POINT: point,
        },
    )
    for index, (name, bounty, look, hear, point) in enumerate(_FIXTURE_DATA)
)

FIXTURE_RULES = Rules(FIXTURE_SPIES, CITIES, LANDMARKS)
