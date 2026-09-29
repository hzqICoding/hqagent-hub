from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter
from protocol.generated.python import models


def test_all_frozen_contract_fixtures_validate_and_round_trip() -> None:
    root = Path(__file__).parents[3] / "packages" / "protocol" / "fixtures" / "contracts"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for filename, model_name in manifest["fixtures"].items():
        raw = json.loads((root / filename).read_text(encoding="utf-8"))
        adapter = TypeAdapter(getattr(models, model_name))
        model = adapter.validate_python(raw)
        assert adapter.dump_python(model, mode="json", by_alias=True, exclude_none=True) == raw
