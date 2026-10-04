"""Cassette replay adapter.

Records from a live provider are stored per case and replayed in CI, so a golden fixture
can be pinned to what a real model actually said rather than to a heuristic stand-in.
A control with no cassette entry is answered as unsupported and the gap is visible in the
trace rather than silently filled.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class ReplayAdapter:
    def __init__(self, cassette: Mapping[str, Any] | str | Path, name: str = "replay"):
        if isinstance(cassette, (str, Path)):
            path = Path(cassette)
            self._data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            self.name = f"replay:{path.stem}"
        else:
            self._data = dict(cassette)
            self.name = name

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        return self._data.get(control_id, {"elements": []})

    @property
    def provenance(self) -> dict[str, Any]:
        """The recording's run manifest (requested and served model, recorded date)."""
        return dict(self._data.get("_run", {}))


class RecordingAdapter:
    """Wraps a live adapter and captures every response into a cassette file."""

    def __init__(self, inner, path: str | Path):
        self._inner = inner
        self._path = Path(path)
        self.name = getattr(inner, "name", "unknown")
        self._captured: dict[str, Any] = {}
        self._meta: dict[str, Any] = {}

    def ask(self, prompt: str, control_id: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        raw = self._inner.ask(prompt, control_id, response_schema)
        self._captured[control_id] = raw
        meta = dict(getattr(self._inner, "last_meta", {}) or {})
        meta["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self._meta[control_id] = meta
        return raw

    def save(self, **run: Any) -> None:
        """Write the cassette. `_run` records what produced it; `_meta` each call's model,
        tokens and prompt hash. Neither holds credentials."""
        served = sorted({m.get("served_model") for m in self._meta.values() if m.get("served_model")})
        doc = {**self._captured,
               "_run": {"adapter": self.name, "served_models": served,
                        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **run},
               "_meta": self._meta}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
