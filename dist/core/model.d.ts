export type Brand<T, B extends string> = T & {
    readonly __brand: B;
};
export type SpyId = Brand<number, "SpyId">;
export type CityId = Brand<number, "CityId">;
export type LandmarkId = Brand<number, "LandmarkId">;
export type QuestionId = Brand<number, "QuestionId">;
export type AnswerCode = Brand<number, "AnswerCode">;
export declare const spyId: (value: number) => SpyId;
export declare const cityId: (value: number) => CityId;
export declare const landmarkId: (value: number) => LandmarkId;
export declare const questionId: (value: number) => QuestionId;
export declare const answerCode: (value: number) => AnswerCode;
export type Faction = "bird" | "sea";
export type Sense = "look" | "hear" | "point";
export type Direction = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";
export interface Coord {
    readonly row: number;
    readonly col: number;
}
export interface Spy {
    readonly id: SpyId;
    readonly name: string;
    readonly faction: Faction;
    readonly bounty: number;
    readonly directions: Readonly<Record<Sense, readonly [Direction] | readonly [Direction, Direction]>>;
}
export interface City {
    readonly id: CityId;
    readonly name: string;
    readonly coord: Coord;
}
export interface Landmark {
    readonly id: LandmarkId;
    readonly name: string;
    readonly coord: Coord;
}
export interface Rules {
    readonly spies: readonly Spy[];
    readonly cities: readonly City[];
    readonly landmarks: readonly Landmark[];
}
export interface Board {
    readonly ringleader: SpyId;
    readonly hideout: CityId;
    /** Index by city id. Null denotes the hideout. */
    readonly occupantByCity: readonly (SpyId | null)[];
}
export interface Question {
    readonly spy: SpyId;
    readonly sense: Sense;
}
export type Answer = {
    readonly kind: "spy";
    readonly spy: SpyId;
} | {
    readonly kind: "landmark";
    readonly landmark: LandmarkId;
} | {
    readonly kind: "nothing";
};
export type QuestionAnswers = readonly [Answer] | readonly [Answer, Answer];
export declare const senses: readonly ["look", "hear", "point"];
export declare const directionDelta: Readonly<Record<Direction, Coord>>;
