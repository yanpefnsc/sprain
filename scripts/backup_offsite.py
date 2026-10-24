"""Copia backups PostgreSQL/PostGIS para um remote rclone crypt.

O destino criptografado deve ser configurado fora do repositório. Nenhum
comando deste script apaga backups, arquivos remotos ou bancos existentes.
"""

from __future__ import annotations

import argparse
import configparser
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from postgres_backup import container_name, database_identifier, verify_archive


REMOTE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*:\Z")
RUN_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{12}\Z")


def checked(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        # A configuração pode conter credenciais. Não incluir stdout/stderr do rclone.
        raise RuntimeError(f"comando falhou com código {result.returncode}: {command[0]}")


def validate_crypt(config_path: Path, remote: str, allow_local_test: bool) -> None:
    if not REMOTE_NAME.fullmatch(remote):
        raise ValueError("--remote deve ser o nome de um remote rclone crypt, com ':' final")
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(config_path, encoding="utf-8"):
        raise ValueError("arquivo de configuração rclone não encontrado")
    name = remote[:-1]
    if name not in parser or parser[name].get("type") != "crypt":
        raise ValueError("o remote informado deve ter type = crypt")
    crypt = parser[name]
    if not crypt.get("password"):
        raise ValueError("o remote crypt não tem senha configurada")
    if crypt.get("no_data_encryption", "false").lower() == "true":
        raise ValueError("criptografia do conteúdo está desativada")
    backing = crypt.get("remote", "")
    if not backing:
        raise ValueError("o remote crypt não aponta para armazenamento")
    if allow_local_test:
        return
    backing_name = backing.split(":", 1)[0]
    if backing_name not in parser or parser[backing_name].get("type") in {None, "local", "crypt"}:
        raise ValueError("o destino deve ser um remote externo configurado; local exige --allow-local-test")


def rclone(args: argparse.Namespace, *parts: str) -> None:
    checked([str(args.rclone_bin), "--config", str(args.config), *parts])


def run(args: argparse.Namespace) -> None:
    validate_crypt(args.config, args.remote, args.allow_local_test)
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    folder = args.staging_dir / args.database / run_id
    folder.mkdir(parents=True, exist_ok=False)
    backup_script = Path(__file__).with_name("postgres_backup.py")
    checked([
        sys.executable, str(backup_script), "backup", "--container", args.container,
        "--database", args.database, "--user", args.user, "--output-dir", str(folder),
    ])
    archives = list(folder.glob("*.dump"))
    if len(archives) != 1:
        raise RuntimeError("a pasta desta execução não contém exatamente um backup completo")
    verify_archive(archives[0])
    destination = f"{args.remote}{args.database}/{run_id}"
    rclone(args, "copy", str(folder), destination, "--immutable")
    rclone(args, "cryptcheck", str(folder), destination)
    print(f"Backup copiado e conferido no destino criptografado: {args.database}/{run_id}")
    print(f"Cópia local preservada em: {folder}")


def fetch(args: argparse.Namespace) -> None:
    validate_crypt(args.config, args.remote, args.allow_local_test)
    folder = args.download_dir / args.database / args.run_id
    folder.mkdir(parents=True, exist_ok=False)
    source = f"{args.remote}{args.database}/{args.run_id}"
    rclone(args, "copy", source, str(folder))
    archives = list(folder.glob("*.dump"))
    if len(archives) != 1:
        raise RuntimeError("o destino remoto não contém exatamente um backup completo")
    metadata = verify_archive(archives[0])
    if metadata.get("source_database") != args.database:
        raise RuntimeError("o banco do manifesto não corresponde ao solicitado")
    print(f"Backup baixado e SHA-256 validado: {archives[0]}")
    print("Restaure apenas em banco novo com scripts/postgres_backup.py restore.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name, action in (("run", run), ("fetch", fetch)):
        command = commands.add_parser(name)
        command.add_argument("--database", type=database_identifier, required=True)
        command.add_argument("--remote", required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--rclone-bin", type=Path, default=Path("rclone"))
        command.add_argument("--allow-local-test", action="store_true")
        command.set_defaults(function=action)
        if name == "run":
            command.add_argument("--container", type=container_name, required=True)
            command.add_argument("--user", type=database_identifier, required=True)
            command.add_argument("--staging-dir", type=Path, required=True)
        else:
            command.add_argument("--run-id", required=True)
            command.add_argument("--download-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "fetch" and not RUN_ID.fullmatch(args.run_id):
        parser.error("--run-id inválido")
    try:
        args.function(args)
    except (OSError, ValueError, RuntimeError, configparser.Error) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
