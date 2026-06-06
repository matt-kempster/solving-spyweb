import { type Board, type Rules } from "../core/model.js";
import type { Encoding } from "./encoding.js";
export declare const EMPTY = 255;
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
export declare function enumerateBoards(rules: Rules): Generator<Board>;
export declare function buildUniverse(rules: Rules, encoding: Encoding, limit?: number): CompactUniverse;
