from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    action: str
    model: str
    record_id: int | None
    payload: dict[str, Any]
    timestamp: str


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(
        self,
        *,
        actor: str,
        action: str,
        model: str,
        record_id: int | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = AuditEvent(
            actor=actor,
            action=action,
            model=model,
            record_id=record_id,
            payload=payload or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")
