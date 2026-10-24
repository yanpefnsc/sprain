"""Confere identidade imutável e revisão declarada da imagem antes do deploy."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


DIGEST = re.compile(r"(?:sha256:[0-9a-f]{64}|[^\s@]+@sha256:[0-9a-f]{64})\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="ID sha256:... ou repositório@sha256:...")
    parser.add_argument("--commit", required=True, help="SHA completo do commit aprovado")
    args = parser.parse_args()
    if not DIGEST.fullmatch(args.image) or not COMMIT.fullmatch(args.commit):
        parser.error("informe digest imutável e SHA Git completo, ambos em hexadecimal minúsculo")
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .}}", args.image],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        print("Docker indisponível", file=sys.stderr)
        return 1
    if result.returncode:
        print("Imagem não encontrada localmente; carregue o digest antes do deploy", file=sys.stderr)
        return 1
    try:
        metadata = json.loads(result.stdout)
        revision = metadata["Config"]["Labels"]["org.opencontainers.image.revision"]
        image_id = metadata["Id"]
    except (KeyError, TypeError, ValueError):
        print("Imagem sem metadados de revisão verificáveis", file=sys.stderr)
        return 1
    if args.image.startswith("sha256:") and image_id != args.image:
        print("ID da imagem não corresponde ao digest solicitado", file=sys.stderr)
        return 1
    if revision != args.commit:
        print("Revisão da imagem não corresponde ao commit aprovado", file=sys.stderr)
        return 1
    print(f"Imagem e revisão conferidas: {image_id} / {revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
