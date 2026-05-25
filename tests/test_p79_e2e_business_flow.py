"""P79 — smoke rutas flujo negocio (sin externos)."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.web.main import web_app


def test_critical_business_routes_registered():
    paths = {getattr(r, "path", None) for r in web_app.routes}
    required = (
        "/casos",
        "/dashboard",
        "/ventas",
        "revision-talon",
        "generar-autorizacion",
    )
    for needle in required:
        assert any(p and needle in p for p in paths), f"missing route containing {needle}"


def test_health_for_e2e_monitoring():
    client = TestClient(web_app)
    assert client.get("/health").status_code == 200


def test_p79_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P79_E2E_BUSINESS_FLOW.md"
    text = doc.read_text(encoding="utf-8")
    assert "compulsa" in text.lower()
    assert "pedido" in text.lower() or "caso" in text.lower()
