"""Sonda externa de disponibilidade com alerta de queda e recuperação via Discord.

Execute em outra máquina. Não modifica dados da aplicação ou do banco.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def valid_url(value: str, allow_local_test: bool) -> str:
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("URL inválida")
    if parsed.scheme != "https" and not (allow_local_test and local and parsed.scheme == "http"):
        raise ValueError("use HTTPS; HTTP é permitido apenas em teste local explícito")
    return value


def probe(url: str, timeout: float) -> tuple[bool, str]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "SPRain-External-Monitor/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False, f"HTTP {response.status}"
            body = response.read(65537)
            if len(body) > 65536:
                return False, "resposta grande demais"
            payload = json.loads(body)
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__
    if not isinstance(payload, dict):
        return False, "resposta inválida"
    if payload.get("status") != "READY" or payload.get("postgis") != "OPERACIONAL":
        return False, "API ou PostGIS indisponível"
    total = payload.get("total_trechos_osm")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        return False, "malha viária indisponível"
    return True, "API, PostGIS e malha operacionais"


def load_state(path: Path, url: str) -> dict:
    if not path.exists():
        return {"url": url, "failures": 0, "alerted": False}
    with path.open(encoding="utf-8") as stream:
        state = json.load(stream)
    if not isinstance(state, dict) or state.get("url") != url:
        raise ValueError("estado pertence a outra URL ou está inválido; use outro arquivo de estado")
    failures = state.get("failures")
    if not isinstance(failures, int) or failures < 0 or not isinstance(state.get("alerted"), bool):
        raise ValueError("arquivo de estado inválido")
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False)
        stream.write("\n")
    os.replace(temporary, path)


def notify(webhook_url: str, message: str, timeout: float) -> None:
    payload = json.dumps({"content": message}, ensure_ascii=False).encode("utf-8")
    request = Request(
        webhook_url, data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "SPRain-External-Monitor/1"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"webhook respondeu HTTP {response.status}")


def check(args: argparse.Namespace) -> int:
    url = valid_url(args.url, args.allow_http_local_test)
    webhook_url = valid_url(args.webhook_url, args.allow_http_local_test)
    state = load_state(args.state_file, url)
    healthy, reason = probe(url, args.timeout)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if healthy:
        state["failures"] = 0
        if state["alerted"]:
            notify(webhook_url, f"SPRain RECUPERADO {stamp}: {reason}", args.timeout)
            state["alerted"] = False
        save_state(args.state_file, state)
        print(reason)
        return 0
    state["failures"] += 1
    save_state(args.state_file, state)
    if state["failures"] >= args.failure_threshold and not state["alerted"]:
        notify(webhook_url, f"SPRain INDISPONÍVEL {stamp}: {reason}", args.timeout)
        state["alerted"] = True
        save_state(args.state_file, state)
    print(f"Indisponível ({state['failures']} falhas seguidas): {reason}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="URL pública HTTPS de /api/v1/health/readiness")
    parser.add_argument("--webhook-url", required=True, help="webhook HTTPS do Discord")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--failure-threshold", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--allow-http-local-test", action="store_true")
    args = parser.parse_args()
    if args.failure_threshold < 1 or not 0 < args.timeout <= 30:
        parser.error("limite de falhas e timeout devem ser positivos (timeout até 30 s)")
    try:
        return check(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, URLError, HTTPError) as exc:
        print(f"Erro no monitor: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
