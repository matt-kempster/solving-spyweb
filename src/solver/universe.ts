import { answerQuestion } from "../core/rules.js";
import { cityId, spyId, type Board, type Rules } from "../core/model.js";
import type { Encoding } from "./encoding.js";

export const EMPTY = 255;

export interface CompactUniverse {
  readonly boardCount: number;
  readonly cityCount: number;
  readonly spyCount: number;
  readonly ringleader: Uint8Array;
  readonly hideout: Uint8Array;
  /** Row-major [board, city], EMPTY denotes hideout. */
  readonly occupantByCity: Uint8Array;
  /** Row-major [question, board], first answer. */
  readonly answer0: Uint8Array;
  /** Row-major [question, board], second answer or same as first. */
  readonly answer1: Uint8Array;
  readonly dualQuestion: Uint8Array;
}

function* permutations(values: readonly number[]): Generator<readonly number[]> {
  if (values.length === 0) {
    yield [];
    return;
  }
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (value === undefined) continue;
    const remaining = values.filter((_, candidate) => candidate !== index);
    for (const tail of permutations(remaining)) yield [value, ...tail];
  }
}

export function enumerateBoards(rules: Rules): Generator<Board> {
  const spyIds = rules.spies.map((spy) => Number(spy.id));
  const cityIds = rules.cities.map((city) => Number(city.id));
  const placementIndexes = spyIds.slice(0, -1);
  return (function* (): Generator<Board> {
    // Interleave all target pairs so limited development universes remain representative.
    for (const placementOrder of permutations(placementIndexes)) {
      for (const ringleader of spyIds) {
        const visible = spyIds.filter((spy) => spy !== ringleader);
        const order = placementOrder.map((index) => visible[index]).filter((spy): spy is number => spy !== undefined);
        for (const hideout of cityIds) {
          const occupiedCities = cityIds.filter((city) => city !== hideout);
          const occupantByCity: (ReturnType<typeof spyId> | null)[] = Array(rules.cities.length).fill(null);
          occupiedCities.forEach((city, index) => {
            const spy = order[index];
            if (spy !== undefined) occupantByCity[city] = spyId(spy);
          });
          yield { ringleader: spyId(ringleader), hideout: cityId(hideout), occupantByCity };
        }
      }
    }
  })();
}

export function buildUniverse(rules: Rules, encoding: Encoding, limit = Number.POSITIVE_INFINITY): CompactUniverse {
  const boards: Board[] = [];
  for (const board of enumerateBoards(rules)) {
    if (boards.length >= limit) break;
    boards.push(board);
  }
  const boardCount = boards.length;
  const occupantByCity = new Uint8Array(boardCount * rules.cities.length);
  const ringleader = new Uint8Array(boardCount);
  const hideout = new Uint8Array(boardCount);
  const answer0 = new Uint8Array(encoding.questionCount * boardCount);
  const answer1 = new Uint8Array(encoding.questionCount * boardCount);
  const dualQuestion = new Uint8Array(encoding.questionCount);

  boards.forEach((board, boardIndex) => {
    ringleader[boardIndex] = board.ringleader;
    hideout[boardIndex] = board.hideout;
    board.occupantByCity.forEach((spy, city) => {
      occupantByCity[boardIndex * rules.cities.length + city] = spy ?? EMPTY;
    });
    for (let q = 0; q < encoding.questionCount; q += 1) {
      const answers = answerQuestion(rules, board, encoding.decodeQuestion(q as ReturnType<Encoding["questionId"]>));
      answer0[q * boardCount + boardIndex] = encoding.answerCode(answers[0]);
      answer1[q * boardCount + boardIndex] = encoding.answerCode(answers[1] ?? answers[0]);
      dualQuestion[q] = answers.length === 2 ? 1 : 0;
    }
  });

  return {
    boardCount,
    cityCount: rules.cities.length,
    spyCount: rules.spies.length,
    ringleader,
    hideout,
    occupantByCity,
    answer0,
    answer1,
    dualQuestion
  };
}
