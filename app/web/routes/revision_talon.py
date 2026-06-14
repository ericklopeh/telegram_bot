from decimal import Decimal
import logging
from typing import Generator

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.case import Case
from app.web.services.talon_review_service import guardar_revision_talon
from app.web.services.revision_talon_calculator import (
    calcular_revision_talon,
    generar_mensaje_vendedor,
)
from app.web.auth import ROLES_ADMIN_SISTEMAS, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

log = logging.getLogger(__name__)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


from app.models.document import Document
from app.models.ocr_result import OcrResult
from app.models.case_history import CaseHistory
from sqlalchemy import desc

@router.get("/casos/{case_id}/revision-talon")
def revision_talon_get(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    redirect = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    valid_types = ["talon", "talón", "revision", "revision_evidencia"]
    documento = db.query(Document).filter(
        Document.case_id == case_id,
        Document.is_active == True,
        Document.document_type.in_(valid_types)
    ).order_by(desc(Document.uploaded_at)).first()

    ocr_result = None
    preview_url = None
    review_fields = []
    form_data = {
        "percepciones": 0,
        "deducciones": 0,
        "liquido": 0,
        "extra": 0,
        "tiene_programados": "NO",
        "monto_programados": 0,
    }

    valid_capacity_keys = {"E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG", "O1"}
    income_items_editable = []

    if documento:
        preview_url = f"/documentos/{documento.id}/ver"
        
        ocr_result = db.query(OcrResult).filter(
            OcrResult.document_id == documento.id
        ).order_by(desc(OcrResult.created_at)).first()
        
        if ocr_result and ocr_result.parsed_json and ocr_result.review_status == 'processed':
            pj = ocr_result.parsed_json
            
            percepciones = pj.get('capacity_income_total')
            if percepciones is None or percepciones <= 0: percepciones = pj.get('percepciones')
            if percepciones is None or percepciones <= 0: percepciones = pj.get('percepciones_total')
                
            deducciones = pj.get('deducciones')
            if deducciones is None: deducciones = pj.get('deducciones_total')
                
            liquido = pj.get('liquido')

            form_data["percepciones"] = percepciones or 0
            form_data["deducciones"] = deducciones or 0
            form_data["liquido"] = liquido or 0

            review_fields = pj.get('review_fields') or []

    # Cargar último mensaje guardado temporalmente en CaseHistory (sin nueva persistencia)
    last_mensaje = None
    try:
        last_history = db.query(CaseHistory).filter(
            CaseHistory.case_id == case_id,
            CaseHistory.notes.like("%Mensaje talón:%")
        ).order_by(desc(CaseHistory.created_at)).first()
        if last_history and last_history.notes:
            # Extraer la parte después de "Mensaje talón: "
            if "Mensaje talón:" in last_history.notes:
                last_mensaje = last_history.notes.split("Mensaje talón:", 1)[1].strip()
    except Exception:
        last_mensaje = None

    return templates.TemplateResponse(
        request=request,
        name="revision_talon.html",
        context={
            "usuario": usuario,
            "caso": caso,
            "documento": documento,
            "preview_url": preview_url,
            "ocr_result": ocr_result,
            "form_data": form_data,
            "review_fields": review_fields,
            "last_mensaje": last_mensaje,
            "resultado": None,
            "mensaje": None,
            "cuentas_liberadas": [],
            "cuentas_observadas": [],
        },
    )


from fastapi import Form
@router.post("/casos/{case_id}/revision-talon")
async def revision_talon_post(
    case_id: int,
    request: Request,
    percepciones: Decimal = Form(Decimal("0")),
    deducciones: Decimal = Form(Decimal("0")),
    liquido: Decimal = Form(Decimal("0")),
    extra: Decimal = Form(Decimal("0")),
    tiene_programados: str = Form("NO"),
    monto_programados: Decimal = Form(Decimal("0")),
    concept_count: int = Form(0),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    redirect = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    # Cargar datos para render (duplicado mínimo del GET para poder mostrar resultado sin redirect)
    valid_types = ["talon", "talón", "revision", "revision_evidencia"]
    documento = db.query(Document).filter(
        Document.case_id == case_id,
        Document.is_active == True,
        Document.document_type.in_(valid_types)
    ).order_by(desc(Document.uploaded_at)).first()

    ocr_result = None
    preview_url = None
    if documento:
        preview_url = f"/documentos/{documento.id}/ver"
        ocr_result = db.query(OcrResult).filter(
            OcrResult.document_id == documento.id
        ).order_by(desc(OcrResult.created_at)).first()

    tiene_programados_bool = tiene_programados == "SI"

    form_data = await request.form()
    
    ingresos_validos = percepciones
    descuentos = deducciones
    liquidez_final = liquido
    resumen_conceptos = []
    
    rf_keys = ["E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG", "O1"]
    
    codigos_extraidos = {}
    
    # Check if we are receiving review fields (supports full code breakdown)
    if "rf_E4" in form_data:
        suma_ingresos = Decimal("0")
        for key in rf_keys:
            val_str = form_data.get(f"rf_{key}", "0")
            try:
                val = Decimal(val_str)
                codigos_extraidos[key] = {"importe": float(val)}
                suma_ingresos += val
                if val > 0:
                    resumen_conceptos.append(f"{key}: ${val:.2f}")
            except:
                codigos_extraidos[key] = {"importe": 0.0}
                
        # D and DC (descuentos)
        val_d = Decimal(form_data.get("rf_D", "0"))
        val_dc = Decimal(form_data.get("rf_DC", "0"))
        
        ingresos_validos = suma_ingresos
        descuentos = val_d + val_dc
        
        # Calculate final liquidity using full logic
        total_70 = ingresos_validos * Decimal("0.70")
        saldo_70 = total_70 - descuentos
        
        prog = monto_programados if tiene_programados_bool else Decimal("0")
        liquidez_final = saldo_70 + extra - prog

    # Support for cuentas terminadas (enriched from Streamlit logic, via form fields ct_0 etc.)
    # For compatibility, current form may not send them; we parse if present.
    cuentas_terminadas = []
    ct_count = int(form_data.get("ct_count", 0) or 0)
    for i in range(min(ct_count, 5)):  # limit to 5 for safety
        qna = form_data.get(f"ct_qna_{i}", "").strip()
        saldo_str = form_data.get(f"ct_saldo_{i}", "0")
        obs = form_data.get(f"ct_obs_{i}", "").strip()
        sumar = form_data.get(f"ct_sumar_{i}", "on") == "on"
        try:
            saldo = float(saldo_str)
        except:
            saldo = 0.0
        if qna or saldo > 0:
            cuentas_terminadas.append({
                "qna_termina": qna or f"QNA-{i+1}",
                "saldo_liberado": saldo,
                "observacion": obs,
                "sumar_a_liquidez": sumar,
            })

    # Build rich revision using migrated full logic
    revision = calcular_revision_talon(
        codigos_extraidos=codigos_extraidos or {"E4": {"importe": float(ingresos_validos or 0)}},
        descuentos_talon=float(descuentos or 0),
        abono_extra=float(extra or 0),
        programado=float(monto_programados or 0),
        cuentas_terminadas=cuentas_terminadas,
    )

    # Generate formal message (migrated logic)
    datos_cliente = {
        "nombre": getattr(caso, "client_name", "") or "Cliente",
        "rfc": "",  # not in basic Case; can be enriched later from documents
    }
    tiene_prog_str = "Sí" if tiene_programados_bool and monto_programados > 0 else "No"
    mensaje = generar_mensaje_vendedor(
        datos=datos_cliente,
        revision=revision,
        tiene_programado=tiene_prog_str,
    )

    guardar_revision_talon(
        db=db,
        case=caso,
        percepciones=ingresos_validos,
        deducciones=descuentos,
        liquido=liquidez_final,
        extra=extra,
        tiene_programados=tiene_programados_bool,
        monto_programados=monto_programados,
        usuario_nombre=usuario.get("nombre", "web_user"),
        # extra for full logic (temporary, not persisted in model yet)
        codigos_extraidos=codigos_extraidos,
        abono_extra=float(extra or 0),
        programado=float(monto_programados or 0),
        cuentas_terminadas=cuentas_terminadas,
        mensaje=mensaje,
    )
    
    if resumen_conceptos:
        from app.models.case_history import CaseHistory
        last_history = db.query(CaseHistory).filter(CaseHistory.case_id == case_id, CaseHistory.action_source == "web").order_by(desc(CaseHistory.created_at)).first()
        if last_history:
            last_history.notes = (last_history.notes or "") + " | Conceptos OCR usados: " + ", ".join(resumen_conceptos)
            db.commit()

    # Append the formal message to history notes (temporary storage until model supports it)
    from app.models.case_history import CaseHistory
    last_history = db.query(CaseHistory).filter(CaseHistory.case_id == case_id, CaseHistory.action_source == "web").order_by(desc(CaseHistory.created_at)).first()
    if last_history:
        last_history.notes = (last_history.notes or "") + " | Mensaje talón: " + (mensaje[:300] if mensaje else "")
        db.commit()
    else:
        # create one if none
        db.add(CaseHistory(
            case_id=case_id,
            old_status=case.current_status,
            new_status=case.current_status,
            action_source="web",
            action_user=usuario.get("nombre", "web_user"),
            notes="Mensaje talón: " + (mensaje[:300] if mensaje else ""),
        ))
        db.commit()

    # En lugar de redirigir siempre, renderizamos el template con los resultados calculados
    # para mostrar el mensaje y desglose directamente (como en Streamlit).
    # Mantenemos compatibilidad: el formulario sigue funcionando.
    # form_data se reconstruye para prellenar.
    updated_form_data = {
        "percepciones": float(ingresos_validos or 0),
        "deducciones": float(descuentos or 0),
        "liquido": float(liquidez_final or 0),
        "extra": float(extra or 0),
        "tiene_programados": "SI" if tiene_programados_bool else "NO",
        "monto_programados": float(monto_programados or 0),
    }
    # Pasar las cuentas para prefill en la UI
    for idx, ct in enumerate(cuentas_terminadas[:2]):
        updated_form_data[f"ct_qna_{idx}"] = ct.get("qna_termina", "")
        updated_form_data[f"ct_saldo_{idx}"] = ct.get("saldo_liberado", 0)
        updated_form_data[f"ct_obs_{idx}"] = ct.get("observacion", "")
        updated_form_data[f"ct_sumar_{idx}"] = "on" if ct.get("sumar_a_liquidez") else ""

    # Reconstruir review_fields si aplica para mantener la vista (en POST puede no existir del OCR)
    current_review_fields = []

    return templates.TemplateResponse(
        request=request,
        name="revision_talon.html",
        context={
            "usuario": usuario,
            "caso": caso,
            "documento": documento,
            "preview_url": preview_url,
            "ocr_result": ocr_result,
            "form_data": updated_form_data,
            "review_fields": current_review_fields,
            "resultado": revision,  # enriquecido con full keys from calculator
            "mensaje": mensaje,
            "cuentas_liberadas": [c for c in cuentas_terminadas if c.get("sumar_a_liquidez")],
            "cuentas_observadas": [c for c in cuentas_terminadas if not c.get("sumar_a_liquidez")],
            "last_mensaje": mensaje,  # for this render it's the current
        },
    )
