import { type City, type Rules, type Spy } from "./model.js";
export declare const cities: readonly City[];
export declare const landmarks: readonly [{
    readonly id: import("./model.js").LandmarkId;
    readonly name: "Car";
    readonly coord: {
        readonly row: 0;
        readonly col: -1;
    };
}, {
    readonly id: import("./model.js").LandmarkId;
    readonly name: "Plane";
    readonly coord: {
        readonly row: -1;
        readonly col: 2;
    };
}, {
    readonly id: import("./model.js").LandmarkId;
    readonly name: "Boat";
    readonly coord: {
        readonly row: 2;
        readonly col: 3;
    };
}];
export declare const fixtureSpies: readonly Spy[];
export declare const fixtureRules: Rules;
