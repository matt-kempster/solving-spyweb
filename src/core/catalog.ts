import {
  cityId,
  landmarkId,
  spyId,
  type City,
  type Direction,
  type Landmark,
  type Rules,
  type Spy
} from "./model.js";

export const cities = [
  ["Montreal", 0, 0],
  ["London", 0, 1],
  ["Moscow", 0, 2],
  ["Washington", 1, 0],
  ["Cairo", 1, 1],
  ["Hong Kong", 1, 2],
  ["Rio de Janeiro", 2, 0],
  ["Cape Town", 2, 1],
  ["Melbourne", 2, 2]
].map(([name, row, col], id) => ({
  id: cityId(id),
  name,
  coord: { row, col }
})) as readonly City[];

export const landmarks = [
  { id: landmarkId(0), name: "Car", coord: { row: 0, col: -1 } },
  { id: landmarkId(1), name: "Plane", coord: { row: -1, col: 2 } },
  { id: landmarkId(2), name: "Boat", coord: { row: 2, col: 3 } }
] as const satisfies readonly Landmark[];

/**
 * Development fixture, not a verified transcription of either physical deck.
 * The dual point on Raven exercises the strategic two-answer rule.
 */
interface FixtureSpy {
  readonly name: string;
  readonly bounty: number;
  readonly look: readonly [Direction] | readonly [Direction, Direction];
  readonly hear: readonly [Direction] | readonly [Direction, Direction];
  readonly point: readonly [Direction] | readonly [Direction, Direction];
}

const fixtureSpyData = [
  { name: "Raven", bounty: 300_000, look: ["w"], hear: ["e"], point: ["n", "s"] },
  { name: "Buzzard", bounty: 300_000, look: ["e"], hear: ["w"], point: ["n"] },
  { name: "Hawk", bounty: 100_000, look: ["w"], hear: ["e"], point: ["s"] },
  { name: "Vulture", bounty: 300_000, look: ["w"], hear: ["e"], point: ["n"] },
  { name: "Osprey", bounty: 200_000, look: ["e"], hear: ["w"], point: ["s"] },
  { name: "Eagle", bounty: 400_000, look: ["e"], hear: ["w"], point: ["nw"] },
  { name: "Condor", bounty: 500_000, look: ["e"], hear: ["n"], point: ["w"] },
  { name: "Falcon", bounty: 400_000, look: ["n"], hear: ["w"], point: ["s"] },
  { name: "Crow", bounty: 300_000, look: ["w"], hear: ["e"], point: ["s"] }
] as const satisfies readonly FixtureSpy[];

export const fixtureSpies: readonly Spy[] = fixtureSpyData.map(({ name, bounty, look, hear, point }, id) => ({
  id: spyId(id),
  name,
  faction: "bird",
  bounty,
  directions: { look, hear, point }
}));

export const fixtureRules: Rules = {
  spies: fixtureSpies,
  cities,
  landmarks
};
