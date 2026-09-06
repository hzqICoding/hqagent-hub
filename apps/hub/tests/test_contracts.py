from __future__ import annotations

import json
from pathlib import Path

from protocol.generated.python import models


def test_all_frozen_contract_fixtures_validate_and_round_trip() -> None:
    root = Path(__file__).parents[3] / "packages" / "protocol" / "fixtures" / "contracts"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for filename, model_name in manifest["fixtures"].items():
        raw = json.loads((root / filename).read_text(encoding="utf-8"))
        model = getattr(models, model_name).model_validate(raw)
        assert model.model_dump(mode="json", by_alias=True, exclude_none=True) == raw

