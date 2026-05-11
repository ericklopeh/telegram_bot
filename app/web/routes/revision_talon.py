from typing import Generator, List

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from decimal import Decimal
from app.db.session import get_db_session
from app.models.case import Case
from app.web.services.talon_review_service import guardar_revision_talon
from app.web.auth import get_current_user, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


from app.models.document import Document
from app.models.ocr_result import OcrResult
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

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    tiene_programados_bool = tiene_programados == "SI"

    form_data = await request.form()
    
    ingresos_validos = percepciones
    descuentos = deducciones
    liquidez_final = liquido
    resumen_conceptos = []
    
    rf_keys = ["E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG", "O1"]
    
    # Check if we are receiving review fields
    if "rf_E4" in form_data:
        suma_ingresos = Decimal("0")
        for key in rf_keys:
            val_str = form_data.get(f"rf_{key}", "0")
            try:
                val = Decimal(val_str)
                suma_ingresos += val
                if val > 0:
                    resumen_conceptos.append(f"{key}: ${val:.2f}")
            except:
                pass
                
        # D and DC
        val_d = Decimal(form_data.get("rf_D", "0"))
        val_dc = Decimal(form_data.get("rf_DC", "0"))
        
        ingresos_validos = suma_ingresos
        descuentos = val_d + val_dc
        
        # Calculate final liquidity
        total_70 = ingresos_validos * Decimal("0.70")
        saldo_70 = total_70 - descuentos
        
        prog = monto_programados if tiene_programados_bool else Decimal("0")
        liquidez_final = saldo_70 + extra - prog

    guardar_revision_talon(
        db=db,
        case=caso,
        percepciones=ingresos_validos,
        deducciones=descuentos,
        liquido=liquidez_final,
        extra=extra,
        tiene_programados=tiene_programados_bool,
        monto_programados=monto_programados,
        usuario_nombre=usuario.get("nombre", "web_user")
    )
    
    if resumen_conceptos:
        from app.models.case_history import CaseHistory
        last_history = db.query(CaseHistory).filter(CaseHistory.case_id == case_id, CaseHistory.action_source == "web").order_by(desc(CaseHistory.created_at)).first()
        if last_history:
            last_history.notes = (last_history.notes or "") + " | Conceptos OCR usados: " + ", ".join(resumen_conceptos)
            db.commit()

    return RedirectResponse(url=f"/casos/{case_id}", status_code=302)
