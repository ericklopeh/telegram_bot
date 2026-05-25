"""P82–P86 — documentación fase final."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

DOCS = [
    ("P82", "P82_REAL_DATA_QA.md", ("mueble", "rollback")),
    ("P83", "P83_INTERNAL_TRAINING.md", ("vendedor", "SOP")),
    ("P84", "P84_PILOT_EXECUTION.md", ("métrica", "piloto")),
    ("P85", "P85_PRODUCTION_ROLLOUT.md", ("go-live", "migrations")),
    ("P86", "P86_EXECUTIVE_PORTFOLIO.md", ("Data Engineer", "FastAPI")),
]


@pytest.mark.parametrize("phase,filename,keywords", DOCS)
def test_phase_doc_exists(phase, filename, keywords):
    path = ROOT / "docs" / filename
    assert path.is_file(), f"{phase} doc missing"
    text = path.read_text(encoding="utf-8").lower()
    for kw in keywords:
        assert kw.lower() in text, f"{phase}: missing {kw}"
