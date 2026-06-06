import type { GameEvent, TraceStep } from "../core/events.js";
import type { Encoding } from "./encoding.js";
import {
  filterFirstAnswer,
  filterPaidSecondAnswer,
  pairCount,
  type Belief
} from "./belief.js";
import type { CompactUniverse } from "./universe.js";

export interface ReplayState {
  readonly belief: Belief;
  readonly trace: readonly TraceStep[];
}

export function applyObservedEvent(
  universe: CompactUniverse,
  encoding: Encoding,
  state: ReplayState,
  event: GameEvent
): ReplayState {
  const before = state.belief;
  let after = before;
  if (event.type === "question-answered") {
    after = filterFirstAnswer(
      universe,
      before,
      encoding.questionId(event.question),
      encoding.answerCode(event.answer)
    );
  } else if (event.type === "second-answer-bought") {
    after = filterPaidSecondAnswer(
      universe,
      before,
      encoding.questionId(event.question),
      encoding.answerCode(event.first),
      encoding.answerCode(event.second)
    );
  } else if (event.type === "accusation-resolved") {
    const matches: number[] = [];
    for (const board of before) {
      const isPair =
        universe.ringleader[board] === event.ringleader &&
        universe.hideout[board] === event.hideout;
      if (isPair === event.correct) matches.push(board);
    }
    after = Uint32Array.from(matches);
  }
  const step: TraceStep = {
    sequence: state.trace.length + 1,
    event,
    boardsBefore: before.length,
    boardsAfter: after.length,
    pairsBefore: pairCount(universe, before),
    pairsAfter: pairCount(universe, after)
  };
  return { belief: after, trace: [...state.trace, step] };
}
