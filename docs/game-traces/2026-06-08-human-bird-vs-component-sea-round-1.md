# Human Bird vs Component Sea AI, Round 1

Captured from the live browser session on June 8, 2026.

This trace is preserved for later analysis of the human player's component-building
strategy and comparison against the current component AI.

## Result

- Human: Bird
- Opponent: Sea AI using `component`
- Winner: Bird
- Winning accusation: Orca in Cairo
- Bird ending money: $400,000
- Sea AI ending money: $100,000
- Bird questions: 9
- Sea AI questions: 9
- Bird ending accusation: correct
- Sea AI ending belief: 2 possible ringleader/hideout pairs across 2 boards
- No extra actions or second-direction answers were purchased

## Human Private Setup

- Ringleader: Hawk
- Hideout: Rio de Janeiro

| City | Occupant |
| --- | --- |
| Montreal | Osprey |
| London | Crow |
| Moscow | Vulture |
| Washington | Buzzard |
| Cairo | Eagle |
| Hong Kong | Raven |
| Rio de Janeiro | Hideout |
| Cape Town | Condor |
| Melbourne | Falcon |

## Complete Move Sequence

Turn-ending events are omitted because every player took exactly one action per turn.

| Ply | Player | Action | Answer/result |
| ---: | --- | --- | --- |
| 1 | Bird | Stingray look | Nothing |
| 2 | Sea AI | Raven look | Eagle |
| 3 | Bird | Shark hear | Nothing |
| 4 | Sea AI | Hawk look | Nothing |
| 5 | Bird | Marlin look | Boat |
| 6 | Sea AI | Vulture look | Crow |
| 7 | Bird | Marlin point | Shark |
| 8 | Sea AI | Osprey hear | Car |
| 9 | Bird | Shark look | Nothing |
| 10 | Sea AI | Buzzard point | Osprey |
| 11 | Bird | Stingray point | Eel |
| 12 | Sea AI | Condor point | Nothing |
| 13 | Bird | Shark point | Beluga |
| 14 | Sea AI | Falcon hear | Condor |
| 15 | Bird | Beluga look | Urchin |
| 16 | Sea AI | Osprey look | Crow |
| 17 | Bird | Piranha hear | Leech |
| 18 | Sea AI | Crow point | Eagle |
| 19 | Bird | Accuse Orca in Cairo | Correct |

## Human Observations

In question order:

1. Stingray look east -> Nothing
2. Shark hear east -> Nothing
3. Marlin look east -> Boat
4. Marlin point north -> Shark
5. Shark look west -> Nothing
6. Stingray point north -> Eel
7. Shark point north -> Beluga
8. Beluga look west -> Urchin
9. Piranha hear east -> Leech
10. Orca in Cairo -> correct accusation

The human's positive deduction graph contained:

- Marlin -> Shark
- Stingray -> Eel
- Shark -> Beluga
- Beluga -> Urchin
- Piranha -> Leech
- Marlin anchored to Boat

The human's Nothing observations were:

- Stingray look east
- Shark hear east
- Shark look west

## Human Thought Process

The human's stated heuristic was to start with Stingray because Stingray has three
available directions. After `Stingray look -> Nothing`, the human deliberately put
Stingray aside instead of over-investing in a spy that might be the ringleader.

The next probe was Shark. After `Shark hear -> Nothing`, the working hypothesis was
that at least one of Stingray or Shark was on an edge, adjacent to the hideout, or
the ringleader. That was acceptable uncertainty, so the human moved on rather than
trying to immediately resolve those Nothing answers.

The Marlin sequence was then used to get a more useful structure. The actual order
was `Marlin look -> Boat` followed by `Marlin point -> Shark`; together, these
answers anchored Marlin at Melbourne and connected Shark immediately north of it.
The user's initial verbal reconstruction had the point answer first, but the
strategic point is unchanged: the Marlin answers created a small anchored component
with only a few possible interpretations before the anchor fully fixed it.

From there, the human tried to expand the component. `Shark look -> Nothing` was a
major clue because Shark was now fixed north of the Melbourne-anchored Marlin. Its
westward Nothing answer identified Cairo as the hideout, shifting the only remaining
problem to finding the ringleader.

That is why the human returned to Stingray. If Stingray had kept producing Nothing
answers, the human would have treated Stingray as a strong ringleader candidate and
possibly been done early. Instead, `Stingray point -> Eel` showed that Stingray was
visible and adjacent to the hideout in Cairo. The remaining play then became a
process of expanding components and ruling out visible spies one by one, eventually
leaving Orca as the ringleader and Cairo as the hideout.

## Component AI Observations

In question order:

1. Raven look west -> Eagle
2. Hawk look west -> Nothing
3. Vulture look west -> Crow
4. Osprey hear west -> Car
5. Buzzard point north -> Osprey
6. Condor point west -> Nothing
7. Falcon hear west -> Condor
8. Osprey look east -> Crow
9. Crow point south -> Eagle

The AI's positive deduction graph contained:

- Raven -> Eagle
- Vulture -> Crow
- Buzzard -> Osprey
- Falcon -> Condor
- Osprey -> Crow
- Crow -> Eagle
- Osprey anchored to Car

The AI's Nothing observations were:

- Hawk look west
- Condor point west

## Initial Analysis Notes

The human established the anchored Marlin-Shark component by ply 7, then expanded it
through Shark-Beluga-Urchin. This matches the intended human strategy: anchor or grow
one useful component, then use Nothing answers and the remaining disconnected spies
to identify the ringleader and hideout.

The current component AI instead created several initially disconnected edges:
Raven-Eagle, Vulture-Crow, Buzzard-Osprey, and Falcon-Condor. It eventually joined
most of them through Osprey-Crow and Crow-Eagle, but the early policy did not strongly
prefer expanding the first component.

One important caveat: after `Raven look -> Eagle`, asking `Eagle look` would add no
information because Eagle looks east directly back at Raven. Raven's unasked dual
point question was the actual available expansion attempt.

The component scorer at capture time prioritized remaining-ringleader metrics before
component expansion. Its dual-question expected metrics also double-counted
overlapping first-answer branches, unfairly penalizing Raven's dual point question.
These are candidates for policy changes before benchmarking the human-style strategy.
