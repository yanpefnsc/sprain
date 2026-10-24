"""A restauração não deve aceitar uma cópia pertencente a outro banco."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_offsite


def test_fetch_rejeita_manifesto_de_outro_banco(tmp_path, monkeypatch):
    def copia_de_ensaio(_args, _acao, _origem, destino):
        folder = Path(destino)
        archive = folder / "sprain-outro-20261021T000000Z-test.dump"
        content = b"backup de outro banco"
        archive.write_bytes(content)
        archive.with_name(f"{archive.name}.json").write_text(json.dumps({
            "format": "pg_dump-custom",
            "archive_file": archive.name,
            "source_database": "outro_banco",
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }), encoding="utf-8")

    monkeypatch.setattr(backup_offsite, "validate_crypt", lambda *_: None)
    monkeypatch.setattr(backup_offsite, "rclone", copia_de_ensaio)
    args = argparse.Namespace(
        config=tmp_path / "rclone.conf", remote="crypt:", allow_local_test=True,
        database="sprain_piloto", run_id="20261021T000000Z-abcdef012345",
        download_dir=tmp_path / "downloads",
    )

    with pytest.raises(RuntimeError, match="banco do manifesto"):
        backup_offsite.fetch(args)
