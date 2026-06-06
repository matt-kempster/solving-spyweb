import type { AnswerCode, CityId, QuestionId, SpyId } from "../core/model.js";
import type { CompactUniverse } from "./universe.js";

export type Belief = Uint32Array;

export interface Partition {
  readonly answer: AnswerCode;
  readonly boards: number;
  readonly pairs: number;
}

export interface QuestionScore {
  readonly question: QuestionId;
  readonly worstBoards: number;
  readonly worstPairs: number;
  readonly partitions: readonly Partition[];
}

export const fullBelief = (universe: CompactUniverse): Belief =>
  Uint32Array.from({ length: universe.boardCount }, (_, index) => index);

export function pairKey(ringleader: SpyId | number, hideout: CityId | number, cityCount: number): number {
  return Number(ringleader) * cityCount + Number(hideout);
}

export function pairCount(universe: CompactUniverse, belief: Belief): number {
  const pairs = new Set<number>();
  for (const board of belief) {
    pairs.add(pairKey(universe.ringleader[board] ?? 0, universe.hideout[board] ?? 0, universe.cityCount));
  }
  return pairs.size;
}

export function filterFirstAnswer(
  universe: CompactUniverse,
  belief: Belief,
  question: QuestionId,
  observed: AnswerCode
): Belief {
  const matches: number[] = [];
  const offset = question * universe.boardCount;
  const dual = universe.dualQuestion[question] === 1;
  for (const board of belief) {
    if (
      universe.answer0[offset + board] === observed ||
      (dual && universe.answer1[offset + board] === observed)
    ) {
      matches.push(board);
    }
  }
  return Uint32Array.from(matches);
}

export function filterPaidSecondAnswer(
  universe: CompactUniverse,
  belief: Belief,
  question: QuestionId,
  first: AnswerCode,
  second: AnswerCode
): Belief {
  const matches: number[] = [];
  const offset = question * universe.boardCount;
  for (const board of belief) {
    const a0 = universe.answer0[offset + board];
    const a1 = universe.answer1[offset + board];
    if ((a0 === first && a1 === second) || (a1 === first && a0 === second)) matches.push(board);
  }
  return Uint32Array.from(matches);
}

export function scoreQuestion(universe: CompactUniverse, belief: Belief, question: QuestionId): QuestionScore {
  const answers = new Set<AnswerCode>();
  const offset = question * universe.boardCount;
  for (const board of belief) {
    answers.add(universe.answer0[offset + board] as AnswerCode);
    if (universe.dualQuestion[question] === 1) answers.add(universe.answer1[offset + board] as AnswerCode);
  }
  const partitions = [...answers].map((answer) => {
    const boards = filterFirstAnswer(universe, belief, question, answer);
    return { answer, boards: boards.length, pairs: pairCount(universe, boards) };
  });
  return {
    question,
    worstBoards: Math.max(...partitions.map((partition) => partition.boards)),
    worstPairs: Math.max(...partitions.map((partition) => partition.pairs)),
    partitions
  };
}

export function rankQuestions(universe: CompactUniverse, belief: Belief): readonly QuestionScore[] {
  return Array.from({ length: universe.dualQuestion.length }, (_, q) =>
    scoreQuestion(universe, belief, q as QuestionId)
  ).sort((a, b) => a.worstPairs - b.worstPairs || a.worstBoards - b.worstBoards);
}
