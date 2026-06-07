from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.model import Rules


@dataclass(frozen=True)
class Crop:
    x: int
    y: int
    width: int
    height: int


def grid_crops(width: int, height: int) -> tuple[Crop, ...]:
    x_edges = [round(column * width / 3) for column in range(4)]
    y_edges = [round(row * height / 3) for row in range(4)]
    return tuple(
        Crop(
            x_edges[column],
            y_edges[row],
            x_edges[column + 1] - x_edges[column],
            y_edges[row + 1] - y_edges[row],
        )
        for row in range(3)
        for column in range(3)
    )


def _dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    record = cast(dict[str, object], json.loads(result.stdout))
    streams = cast(list[dict[str, object]], record["streams"])
    return int(cast(int, streams[0]["width"])), int(cast(int, streams[0]["height"]))


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def _slice_sheet(source: Path, output: Path, rules: Rules) -> dict[str, str]:
    width, height = _dimensions(source)
    faction = rules.spies[0].faction.value
    destination = output / "cards" / faction
    destination.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for spy, crop in zip(rules.spies, grid_crops(width, height), strict=True):
        filename = f"{_slug(spy.name)}.png"
        target = destination / filename
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vf",
                f"crop={crop.width}:{crop.height}:{crop.x}:{crop.y}",
                str(target),
            ],
            check=True,
        )
        manifest[spy.name] = f"/local_art/cards/{faction}/{filename}"
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Slice local 3x3 Spy Web card-sheet scans into browser assets"
    )
    parser.add_argument("--bird", type=Path, required=True, help="local Bird card-sheet image")
    parser.add_argument("--sea", type=Path, required=True, help="local Sea card-sheet image")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("spyweb/web_static/local_art"),
        help="git-ignored local browser-art directory",
    )
    args = parser.parse_args(argv)
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required to slice card sheets")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "cards": {
            "bird": _slice_sheet(args.bird, args.output, BIRD_RULES),
            "sea": _slice_sheet(args.sea, args.output, SEA_RULES),
        }
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote local card art and manifest to {args.output}")


if __name__ == "__main__":
    main()
