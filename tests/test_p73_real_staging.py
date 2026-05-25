"""P73 — documentación ambiente staging real."""

from pathlib import Path


def test_p73_doc_exists_and_covers_hosting_options():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P73_REAL_STAGING_ENVIRONMENT.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    for keyword in ("Heroku", "Render", "VPS", "DATABASE_URL", "rollback", "migraciones"):
        assert keyword.lower() in text.lower() or keyword in text
