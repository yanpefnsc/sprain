from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from .worker_status import write_status
else:
    from worker_status import write_status

logger = logging.getLogger(__name__)

IMPORTADOR = Path(__file__).with_name("sincronizar_dados_publicos.py")
FONTES = ("artesp", "anp", "anp-cadastro", "ssp-roubo")

def disparar_alerta(fonte: str, erro: str) -> None:
    webhook_url = os.getenv("WEBHOOK_ALERTA_DADOS")
    if not webhook_url:
        return
    payload = {
        "evento": "FALHA_IMPORTACAO_DADOS_PUBLICOS",
        "fonte": fonte,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "erro": erro[-1000:]
    }
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Falha ao enviar alerta para webhook: {e}", file=sys.stderr, flush=True)

def executar_rodada(heartbeat=None) -> bool:
    overall_success = True
    for fonte in FONTES:
        if heartbeat:
            heartbeat(fonte)
        cmd = [sys.executable, "-B", str(IMPORTADOR), fonte, "--aplicar"]
        try:
            result = subprocess.run(cmd, timeout=600, capture_output=True, text=True, check=False)
        except subprocess.TimeoutExpired as e:
            logger.warning("Fonte timed out: %s: %s", fonte, e)
            overall_success = False
            disparar_alerta(fonte, str(e))
            continue
        except Exception as e:
            logger.exception("Erro executando fonte %s: %s", fonte, e)
            overall_success = False
            disparar_alerta(fonte, str(e))
            continue

        rc = getattr(result, "returncode", 0)
        if rc != 0:
            logger.warning("Fonte %s retornou codigo %s", fonte, rc)
            overall_success = False
            err_msg = getattr(result, "stderr", "Erro desconhecido")
            disparar_alerta(fonte, err_msg)
        else:
            stdout = getattr(result, "stdout", "")
            if stdout:
                print(stdout.strip(), flush=True)
    return overall_success

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Executa uma rodada e termina")
    args = parser.parse_args()
    horas = int(os.getenv("DADOS_PUBLICOS_INTERVALO_HORAS", "24"))
    if not 1 <= horas <= 168:
        parser.error("DADOS_PUBLICOS_INTERVALO_HORAS deve estar entre 1 e 168.")
    last_result = None
    while True:
        print(f"{datetime.now(timezone.utc).isoformat()} Iniciando rodada de importacao...", flush=True)
        write_status("running", horas, last_result=last_result)
        sucesso = executar_rodada(
            heartbeat=lambda fonte: write_status(
                "running", horas, last_result=last_result, source=fonte
            )
        )
        last_result = "ok" if sucesso else "failed"
        write_status("sleeping", horas, last_result=last_result)
        print(f"{datetime.now(timezone.utc).isoformat()} Rodada concluida.", flush=True)
        if args.once:
            raise SystemExit(0 if sucesso else 1)
        time.sleep(horas * 3600)

if __name__ == "__main__":
    main()
