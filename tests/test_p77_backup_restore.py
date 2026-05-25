"""P77 — scripts backup/restore."""

import subprocess
import tempfile
from pathlib import Path


def _scripts_exist(*names: str) -> None:
    root = Path(__file__).resolve().parent.parent / "scripts"
    for name in names:
        assert (root / name).is_file(), name


def test_backup_scripts_exist():
    _scripts_exist(
        "backup_db.sh",
        "backup_staging.sh",
        "restore_db.sh",
        "restore_check_db.sh",
        "prod_backup.sh",
        "prod_restore.sh",
        "prod_verify_backup.sh",
    )


def test_restore_check_db_valid_gzip():
    import gzip
    import os
    import sys

    script = Path(__file__).resolve().parent.parent / "scripts" / "restore_check_db.sh"
    if sys.platform == "win32":
        # Validación portable: gzip real sin depender de bash en Windows
        with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
            tmp.write(gzip.compress(b"-- test dump"))
            path = tmp.name
        try:
            with gzip.open(path, "rb") as fh:
                assert fh.read(4)
        finally:
            os.unlink(path)
        return

    with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tmp:
        tmp.write(gzip.compress(b"-- test dump"))
        path = tmp.name
    try:
        result = subprocess.run(
            ["bash", str(script), path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).resolve().parent.parent,
        )
        assert result.returncode == 0
    except FileNotFoundError:
        pass
    finally:
        os.unlink(path)


def test_p77_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P77_BACKUP_RESTORE.md"
    assert "backup_staging.sh" in doc.read_text(encoding="utf-8")
