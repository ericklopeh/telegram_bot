"""P80 — plan piloto producción."""

from pathlib import Path


def test_p80_doc_covers_pilot_week():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P80_PILOT_PRODUCTION_PLAN.md"
    text = doc.read_text(encoding="utf-8")
    assert "vendedor" in text.lower()
    assert "rollback" in text.lower()
    assert "métrica" in text.lower() or "metrica" in text.lower()
