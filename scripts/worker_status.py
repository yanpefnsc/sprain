"""Estado local do worker de dados públicos para o healthcheck do Docker."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path


STATUS_FILE = Path(tempfile.gettempdir()) / "sprain_dados_worker_status.json"
PROGRESS_TIMEOUT_SECONDS = 15 * 60
SLEEP_GRACE_SECONDS = 15 * 60


def write_status(
    phase: str,
    interval_hours: int,
    *,
    last_result: str | None = None,
    source: str | None = None,
    path: Path = STATUS_FILE,
    now: float | None = None,
) -> None:
    if phase not in ("running", "sleeping") or not 1 <= interval_hours <= 168:
        raise ValueError("estado ou intervalo do worker inválido")
    status = {
        "phase": phase,
        "updated_at_unix": time.time() if now is None else now,
        "interval_seconds": interval_hours * 3600,
        "last_result": last_result,
        "source": source,
    }
    path = Path(path)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(status, stream)
    os.replace(temporary, path)


def check_status(path: Path = STATUS_FILE, now: float | None = None) -> tuple[bool, str]:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            status = json.load(stream)
    except (OSError, ValueError):
        return False, "estado do worker ausente ou inválido"

    if not isinstance(status, dict):
        return False, "estado do worker inválido"
    phase = status.get("phase")
    updated_at = status.get("updated_at_unix")
    interval = status.get("interval_seconds")
    if (
        phase not in ("running", "sleeping")
        or not isinstance(updated_at, (int, float))
        or isinstance(updated_at, bool)
        or not math.isfinite(updated_at)
        or not isinstance(interval, (int, float))
        or isinstance(interval, bool)
        or not 3600 <= interval <= 168 * 3600
    ):
        return False, "estado do worker inválido"

    age = (time.time() if now is None else now) - updated_at
    if age < 0:
        return False, "relógio do estado do worker está no futuro"
    if status.get("last_result") == "failed":
        return False, "última rodada de importação falhou"
    if phase == "running":
        if age > PROGRESS_TIMEOUT_SECONDS:
            return False, "worker não avançou para a próxima fonte"
        return True, "worker executando"
    if status.get("last_result") != "ok":
        return False, "worker ainda não concluiu uma rodada"
    if age > interval + SLEEP_GRACE_SECONDS:
        return False, "worker não iniciou a próxima rodada no prazo"
    return True, "worker aguardando a próxima rodada"


if __name__ == "__main__":
    healthy, message = check_status()
    print(message)
    sys.exit(0 if healthy else 1)
