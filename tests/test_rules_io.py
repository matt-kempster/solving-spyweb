import json
from dataclasses import replace
from pathlib import Path

import pytest

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.model import Sense
from spyweb.core.rules import rules_fingerprint
from spyweb.core.rules_io import read_rules, write_rules


def test_rules_json_round_trip_preserves_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "rules.json"

    write_rules(FIXTURE_RULES, path)
    loaded = read_rules(path)

    assert loaded == FIXTURE_RULES
    assert rules_fingerprint(loaded) == rules_fingerprint(FIXTURE_RULES)
    assert loaded.spies[0].directions[Sense.HEAR] == ()


def test_rules_json_rejects_unknown_direction(tmp_path: Path) -> None:
    path = tmp_path / "rules.json"
    write_rules(FIXTURE_RULES, path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["spies"][0]["directions"]["look"] = ["SIDEWAYS"]
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown direction"):
        read_rules(path)


def test_rules_writer_validates_dense_ids(tmp_path: Path) -> None:
    invalid = replace(
        FIXTURE_RULES,
        spies=(
            replace(FIXTURE_RULES.spies[0], id=FIXTURE_RULES.spies[1].id),
            *FIXTURE_RULES.spies[1:],
        ),
    )

    with pytest.raises(ValueError, match="dense and ordered"):
        write_rules(invalid, tmp_path / "rules.json")
