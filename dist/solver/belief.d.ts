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
export declare const fullBelief: (universe: CompactUniverse) => Belief;
export declare function pairKey(ringleader: SpyId | number, hideout: CityId | number, cityCount: number): number;
export declare function pairCount(universe: CompactUniverse, belief: Belief): number;
export declare function filterFirstAnswer(universe: CompactUniverse, belief: Belief, question: QuestionId, observed: AnswerCode): Belief;
export declare function filterPaidSecondAnswer(universe: CompactUniverse, belief: Belief, question: QuestionId, first: AnswerCode, second: AnswerCode): Belief;
export declare function scoreQuestion(universe: CompactUniverse, belief: Belief, question: QuestionId): QuestionScore;
export declare function rankQuestions(universe: CompactUniverse, belief: Belief): readonly QuestionScore[];
