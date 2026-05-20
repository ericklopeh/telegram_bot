"""Capa OCR reutilizable: extracción, normalización y persistencia en ocr_results."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.document import Document
from app.models.ocr_result import OcrResult

logger = logging.getLogger(__name__)

OCR_ELIGIBLE_DOCUMENT_TYPES = frozenset(
    {
        "talon",
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
    }
)

# --- Heurísticas talón (SNTE) ---

PERCEPCIONES = [
    "SUELDO BASE",
    "COMPENSACION",
    "DESPENSA",
    "ESTIMULO",
    "PRIMA VACACIONAL",
    "AGUINALDO",
    "PRIMA DOMINICAL",
    "OTRAS PERCEPCIONES",
    "TOTAL PERCEPCIONES",
]
DEDUCCIONES = [
    "ISR",
    "IMSS",
    "PENSION ALIMENTICIA",
    "PRESTAMO FOVISSSTE",
    "PRESTAMO INFONAVIT",
    "OTRAS DEDUCCIONES",
    "TOTAL DEDUCCIONES",
    "LIQUIDO A PAGAR",
]
CAPACIDAD_CODES = ["E4", "Q", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"]

RFC_RE = re.compile(r"\b([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})\b", re.IGNORECASE)
FOLIO_RE = re.compile(r"\b(PED[-\s]?\d+|FOLIO[:\s]*([A-Z0-9\-]+))\b", re.IGNORECASE)
PLAZO_RE = re.compile(r"(\d{1,3})\s*(?:quincenas?|qnas?|QNA)", re.IGNORECASE)
MONTO_RE = re.compile(r"\$?\s*([\d,]+\.\d{2})")
NOMBRE_RE = re.compile(
    r"(?:NOMBRE(?:\s+DEL\s+TRABAJADOR)?|CLIENTE|BENEFICIARIO)[:\s]+([A-ZÁÉÍÓÚÑ\s\.]+)",
    re.IGNORECASE,
)
SECCION_RE = re.compile(r"(?:SECCI[ÓO]N|CATEGOR[ÍI]A)[:\s]+([A-Z0-9\s\-]+)", re.IGNORECASE)
PLAZA_RE = re.compile(r"PLAZA[:\s]+([A-ZÁÉÍÓÚÑ0-9\s\-]+)", re.IGNORECASE)
TIPO_EMPLEADO_RE = re.compile(
    r"(?:TIPO\s+(?:DE\s+)?(?:EMPLEADO|TRABAJADOR)|R[ÉE]GIMEN)[:\s]+([A-ZÁÉÍÓÚÑ\s]+)",
    re.IGNORECASE,
)


def _field(value: Any, confidence: float, source: str) -> dict[str, Any]:
    return {"value": value, "confidence": round(confidence, 2), "source": source}


def _parse_amount(text: str) -> float | None:
    if not text:
        return None
    clean = text.replace(",", "").replace("$", "").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def _find_amount_after_label(text: str, label: str) -> float | None:
    pattern = re.compile(re.escape(label) + r"\s*\$?\s*([\d,]+\.\d{2})", re.IGNORECASE)
    match = pattern.search(text)
    if match:
        return _parse_amount(match.group(1))
    return None


def extract_talon_fields(text: str) -> dict[str, Any]:
    """Extrae percepciones, deducciones, líquido y códigos de capacidad del talón."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    percepciones: dict[str, float] = {}
    deducciones: dict[str, float] = {}
    liquido: float | None = None
    codigos: list[str] = []

    for label in PERCEPCIONES:
        amount = _find_amount_after_label(text, label)
        if amount is not None:
            percepciones[label] = amount

    for label in DEDUCCIONES:
        amount = _find_amount_after_label(text, label)
        if amount is not None:
            deducciones[label] = amount
            if label == "LIQUIDO A PAGAR":
                liquido = amount

    for code in CAPACIDAD_CODES:
        if re.search(rf"\b{code}\b", text):
            codigos.append(code)

    review_fields: dict[str, Any] = {}
    for key, val in percepciones.items():
        review_fields[f"percepcion_{key.lower().replace(' ', '_')}"] = _field(val, 0.75, "talon")
    for key, val in deducciones.items():
        review_fields[f"deduccion_{key.lower().replace(' ', '_')}"] = _field(val, 0.75, "talon")
    if liquido is not None:
        review_fields["salario_neto"] = _field(liquido, 0.8, "talon")
    if codigos:
        review_fields["claves_capacidad"] = _field(", ".join(codigos), 0.7, "talon")

    percepciones_total = sum(percepciones.values()) if percepciones else None
    deducciones_total = (
        sum(v for k, v in deducciones.items() if k != "LIQUIDO A PAGAR")
        if deducciones
        else None
    )

    return {
        "percepciones": percepciones,
        "deducciones": deducciones,
        "liquido": liquido,
        "percepciones_total": percepciones_total,
        "deducciones_total": deducciones_total,
        "codigos_capacidad": codigos,
        "review_fields": review_fields,
    }


def extract_generic_fields(text: str, source: str) -> dict[str, Any]:
    """Heurísticas para pedido, orden de descuento y carátula bancaria."""
    fields: dict[str, Any] = {}

    rfc_match = RFC_RE.search(text)
    if rfc_match:
        fields["rfc"] = _field(rfc_match.group(1).upper(), 0.9, source)

    nombre_match = NOMBRE_RE.search(text)
    if nombre_match:
        nombre = nombre_match.group(1).strip()[:120]
        fields["nombre"] = _field(nombre, 0.75, source)

    seccion_match = SECCION_RE.search(text)
    if seccion_match:
        fields["seccion"] = _field(seccion_match.group(1).strip()[:80], 0.7, source)

    plaza_match = PLAZA_RE.search(text)
    if plaza_match:
        fields["plaza"] = _field(plaza_match.group(1).strip()[:80], 0.7, source)

    tipo_match = TIPO_EMPLEADO_RE.search(text)
    if tipo_match:
        fields["tipo_empleado"] = _field(tipo_match.group(1).strip()[:60], 0.65, source)

    folio_match = FOLIO_RE.search(text)
    if folio_match:
        folio = (folio_match.group(2) or folio_match.group(1)).strip()
        fields["folio"] = _field(folio, 0.7, source)

    plazo_match = PLAZO_RE.search(text)
    if plazo_match:
        plazo = int(plazo_match.group(1))
        if plazo in (12, 24, 36, 48, 60, 72, 84, 96):
            fields["plazo_qnas"] = _field(str(plazo), 0.75, source)

    montos = [_parse_amount(m.group(1)) for m in MONTO_RE.finditer(text)]
    montos = [m for m in montos if m is not None and m > 0]
    if montos:
        fields["monto_total"] = _field(max(montos), 0.6, source)

    producto_match = re.search(
        r"(?:PRODUCTO|ART[ÍI]CULO|DESCRIPCI[ÓO]N)[:\s]+(.{3,80})",
        text,
        re.IGNORECASE,
    )
    if producto_match:
        fields["prod_1_nombre"] = _field(producto_match.group(1).strip(), 0.65, source)

    return {"review_fields": fields}


class OCRService:
    """Servicio OCR: extracción, parseo, normalización y persistencia."""

    def __init__(self, db: Session):
        self.db = db

    def extract_from_pdf(self, file_path: str) -> tuple[str, float]:
        try:
            import fitz  # pymupdf
        except ImportError:
            logger.warning("pymupdf no instalado; OCR PDF no disponible")
            return "", 0.0

        if not os.path.isfile(file_path):
            return "", 0.0

        parts: list[str] = []
        try:
            doc = fitz.open(file_path)
            for page in doc:
                parts.append(page.get_text("text"))
            doc.close()
        except Exception as exc:
            logger.exception("Error leyendo PDF %s: %s", file_path, exc)
            return "", 0.0

        raw = "\n".join(parts).strip()
        confidence = 0.85 if len(raw) > 50 else 0.5
        return raw, confidence

    def extract_from_image(self, file_path: str) -> tuple[str, float]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning("pytesseract/Pillow no instalado; OCR imagen no disponible")
            return "", 0.0

        if not os.path.isfile(file_path):
            return "", 0.0

        try:
            img = Image.open(file_path)
            raw = pytesseract.image_to_string(img, lang="spa")
            raw = raw.strip()
            confidence = 0.7 if len(raw) > 30 else 0.45
            return raw, confidence
        except Exception as exc:
            logger.exception("Error OCR imagen %s: %s", file_path, exc)
            return "", 0.0

    def extract_text(self, file_path: str) -> tuple[str, float]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self.extract_from_pdf(file_path)
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"):
            return self.extract_from_image(file_path)
        return "", 0.0

    def parse_document(self, document_type: str, raw_text: str) -> dict[str, Any]:
        if not raw_text:
            return {"review_fields": {}, "raw_empty": True}

        if document_type == "talon":
            parsed = extract_talon_fields(raw_text)
            parsed["document_kind"] = "talon"
            return parsed

        generic = extract_generic_fields(raw_text, document_type)
        generic["document_kind"] = document_type
        return generic

    def normalize_fields(self, parsed_chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Fusiona campos de varios documentos OCR en valores de formulario SNTE."""
        meta: dict[str, dict[str, Any]] = {}
        form: dict[str, Any] = {}

        priority = ["talon", C.DOC_PEDIDO, C.DOC_ORDEN_DESCUENTO, C.DOC_CARATULA_BANCARIA]

        def _merge_key(key: str, field: dict[str, Any], source: str) -> None:
            conf = field.get("confidence", 0.0)
            val = field.get("value")
            if val is None or val == "":
                return
            existing = meta.get(key)
            if existing is None or conf >= existing.get("confidence", 0):
                meta[key] = {"value": val, "confidence": conf, "source": source}

        for kind in priority:
            for chunk in parsed_chunks:
                if chunk.get("document_kind") != kind:
                    continue
                source = kind
                review = chunk.get("review_fields") or {}
                for key, field in review.items():
                    if key.startswith(("percepcion_", "deduccion_", "claves_", "salario_neto")):
                        _merge_key(key, field, source)
                        continue
                    form_key = key
                    if key == "seccion":
                        form_key = "categoria"
                    _merge_key(form_key, field, source)

        # Talón → descuento quincenal estimado
        liquido = meta.get("salario_neto") or meta.get("deduccion_liquido_a_pagar")
        plazo = meta.get("plazo_qnas")
        if liquido and plazo and "descuento_qna" not in meta:
            try:
                liq_val = float(liquido["value"])
                plazo_val = int(plazo["value"])
                if plazo_val > 0:
                    est = round(liq_val / plazo_val, 2)
                    meta["descuento_qna"] = _field(est, 0.55, "talon")
            except (TypeError, ValueError):
                pass

        for key, info in meta.items():
            if not key.startswith(("percepcion_", "deduccion_", "claves_")):
                form[key] = info["value"]

        return {
            "form": form,
            "meta": meta,
            "has_data": bool(meta),
        }

    def process_document(
        self,
        document_id: int,
        action_user: str | None = None,
        *,
        source: str = "system",
    ) -> OcrResult | None:
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning("OCR: documento %s no encontrado", document_id)
            return None

        if doc.document_type not in OCR_ELIGIBLE_DOCUMENT_TYPES:
            logger.info("OCR: tipo %s no elegible", doc.document_type)
            return None

        file_path = doc.file_path or ""
        raw_text, base_conf = self.extract_text(file_path)
        parsed = self.parse_document(doc.document_type, raw_text)
        parsed["document_kind"] = doc.document_type
        parsed["action_user"] = action_user
        parsed["processed_at"] = datetime.utcnow().isoformat()

        review_status = "processed" if raw_text else "error"
        confidence = base_conf
        if parsed.get("review_fields"):
            confs = [f.get("confidence", 0) for f in parsed["review_fields"].values()]
            if confs:
                confidence = round(sum(confs) / len(confs), 2)

        result = OcrResult(
            document_id=doc.id,
            raw_text=raw_text[:50000] if raw_text else None,
            parsed_json=parsed,
            confidence_score=confidence,
            review_status=review_status,
        )
        self.db.add(result)
        try:
            from app.services.case_event_service import log_ocr_event

            log_ocr_event(
                self.db,
                case_id=doc.case_id,
                document_id=doc.id,
                document_type=doc.document_type,
                review_status=review_status,
                confidence=confidence,
                action_user=action_user,
                source=source,
            )
        except Exception:
            logger.exception("No se pudo registrar evento OCR case_id=%s", doc.case_id)
        self.db.commit()
        self.db.refresh(result)
        logger.info(
            "OCR procesado doc=%s tipo=%s conf=%.2f chars=%d",
            document_id,
            doc.document_type,
            confidence,
            len(raw_text or ""),
        )
        return result

    @classmethod
    def build_case_autorizacion_prefill(cls, db: Session, case_id: int) -> dict[str, Any]:
        """Agrega OCR del caso para precargar modal de autorización SNTE."""
        rows = (
            db.query(OcrResult, Document)
            .join(Document, OcrResult.document_id == Document.id)
            .filter(
                Document.case_id == case_id,
                Document.is_active == True,
                OcrResult.review_status == "processed",
                Document.document_type.in_(OCR_ELIGIBLE_DOCUMENT_TYPES),
            )
            .order_by(OcrResult.created_at.desc())
            .all()
        )

        seen_types: set[str] = set()
        chunks: list[dict[str, Any]] = []
        for ocr, document in rows:
            if document.document_type in seen_types:
                continue
            seen_types.add(document.document_type)
            if ocr.parsed_json:
                chunk = dict(ocr.parsed_json)
                chunk["document_kind"] = document.document_type
                chunks.append(chunk)

        svc = cls(db)
        normalized = svc.normalize_fields(chunks)
        normalized["documents_with_ocr"] = list(seen_types)
        return normalized
