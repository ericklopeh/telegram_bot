"""Generación de autorizaciones (Excel) con openpyxl."""

import json
import logging
import os
import uuid
from datetime import datetime

import openpyxl
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.models.authorization_job import AuthorizationJob
from app.models.case import Case
from app.models.document import Document
from app.models.talon_review import TalonReview
from app.services.document_service import DocumentService, StoredIncomingFile

log = logging.getLogger(__name__)


class TemplateNotFoundError(Exception):
    pass


class AuthorizationService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.doc_service = DocumentService()

    def generate_for_case(self, case_id: int, action_user: str) -> Document:
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise ValueError(f"Caso {case_id} no encontrado")

        template_path = self.settings.snte_template_path
        if not os.path.exists(template_path):
            raise TemplateNotFoundError(f"Falta plantilla Excel en: {template_path}")

        mapping_path = self.settings.snte_mapping_path
        if not os.path.exists(mapping_path):
            raise FileNotFoundError(f"Falta mapeo JSON en: {mapping_path}")

        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        talon_review = (
            self.db.query(TalonReview)
            .filter(TalonReview.case_id == case.id)
            .order_by(TalonReview.created_at.desc())
            .first()
        )

        wb = openpyxl.load_workbook(template_path)
        ws = wb.active

        # Mapeo de datos básicos
        def set_cell(key: str, value: str | int | float | None):
            cell_ref = mapping.get(key)
            if cell_ref and value is not None:
                ws[cell_ref] = value

        set_cell("cliente", case.client_name)
        set_cell("folio", case.official_folio or case.temp_folio)
        set_cell("vendedor", case.seller_name)
        set_cell("tipo_venta", case.order_type)
        set_cell("fecha_generacion", datetime.now().strftime("%d/%m/%Y"))

        # El RFC y Monto podrían venir de un perfil o configurarse.
        # Por ahora enviamos PENDIENTE o lo que tengamos.
        set_cell("rfc", "PENDIENTE")
        set_cell("monto_credito", "PENDIENTE")
        set_cell("plazo", "PENDIENTE")

        if talon_review:
            set_cell("percepciones", float(talon_review.percepciones))
            set_cell("deducciones", float(talon_review.deducciones))
            set_cell("liquido", float(talon_review.liquidez_final))
        else:
            set_cell("percepciones", "PENDIENTE")
            set_cell("deducciones", "PENDIENTE")
            set_cell("liquido", "PENDIENTE")

        # Preparar ruta destino local
        upload_dir = self.doc_service.pedido_evidencias_dir(case)
        os.makedirs(upload_dir, exist_ok=True)

        filename = f"{uuid.uuid4()}_autorizacion.xlsx"
        abs_path = os.path.join(upload_dir, filename)

        wb.save(abs_path)

        # Crear AuthorizationJob
        job = AuthorizationJob(
            case_id=case.id,
            template_name=os.path.basename(template_path),
            output_path=abs_path,
            generation_status="success"
        )
        self.db.add(job)

        # Registrar en Document
        stored_file = StoredIncomingFile(
            stored_filename=filename,
            file_abs_path=abs_path,
            original_filename=f"Autorizacion_{case.client_name}.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        doc, present = self.doc_service.register_pedido_document_upload(
            self.db,
            case,
            C.DOC_AUTORIZACION_SNTE,
            stored_file
        )

        self.db.commit()
        return doc
