import type { GameEvent, TraceStep } from "../core/events.js";
import type { Encoding } from "./encoding.js";
import { type Belief } from "./belief.js";
import type { CompactUniverse } from "./universe.js";
export interface ReplayState {
    readonly belief: Belief;
    readonly trace: readonly TraceStep[];
}
export declare function applyObservedEvent(universe: CompactUniverse, encoding: Encoding, state: ReplayState, event: GameEvent): ReplayState;
