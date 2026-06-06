import type { Answer, CityId, Question, SpyId } from "./model.js";
export type Player = "bird" | "sea";
export type GameEvent = {
    readonly type: "question-answered";
    readonly asker: Player;
    readonly question: Question;
    readonly answer: Answer;
} | {
    readonly type: "second-answer-bought";
    readonly asker: Player;
    readonly question: Question;
    readonly first: Answer;
    readonly second: Answer;
    readonly cost: 100_000;
} | {
    readonly type: "accusation-resolved";
    readonly accuser: Player;
    readonly ringleader: SpyId;
    readonly hideout: CityId;
    readonly correct: boolean;
} | {
    readonly type: "extra-action-bought";
    readonly player: Player;
    readonly cost: 100_000;
} | {
    readonly type: "turn-ended";
    readonly player: Player;
};
export interface TraceStep {
    readonly sequence: number;
    readonly event: GameEvent;
    readonly boardsBefore: number;
    readonly boardsAfter: number;
    readonly pairsBefore: number;
    readonly pairsAfter: number;
}
