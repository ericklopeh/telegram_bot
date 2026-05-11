import urllib.parse

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.models.case import Case
from app.models.user import UserRole
from app.services.authorization_service import AuthorizationService, TemplateNotFoundError
from app.services.sharepoint_document_service import SharePointDocumentService, SharePointUploadPayload
from app.web.auth import get_current_user, require_roles

router = APIRouter()

def get_web_db():
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.post("/casos/{case_id}/generar-autorizacion")
async def generar_autorizacion(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_web_db)
):
    # Proteger por roles
    redirect = require_roles(
        request, 
        db, 
        [UserRole.ADMIN.value, UserRole.SISTEMAS.value, UserRole.AUTORIZACION.value]
    )
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

    form = await request.form()
    form_data = dict(form)

    auth_service = AuthorizationService(db)

    try:
        docs = auth_service.generate_for_case(case_id, form_data, action_user)
        
        # 1. Transicionar estatus del caso
        from app.services.case_service import CaseService
        from app.config import get_settings
        from app.domain import constants as C
        
        case_svc = CaseService(get_settings())
        case_svc.transition_case_status(
            db, 
            case, 
            C.ST_PED_AUT_GENERADA, 
            notes="Autorización SNTE generada", 
            action_user=action_user
        )

        # 2. Notificar por Telegram vía background_tasks
        from app.services.notification_service import notify_snte_generation_from_web
        background_tasks.add_task(notify_snte_generation_from_web, case_id)

        # 3. Subir a SharePoint vía background_tasks
        
        sp_service = SharePointDocumentService()
        for doc in docs:
            payload = SharePointUploadPayload(
                document_id=doc.id,
                file_path=doc.file_path,
                vendedor=case.seller_name or "SIN VENDEDOR",
                semana=case.week_code,
                cliente=case.client_name,
                folio=case.official_folio or case.temp_folio or case.public_id,
                tipo_documento=doc.document_type,
                filename=doc.stored_filename
            )
            background_tasks.add_task(sp_service.upload_document, payload)

        msg = urllib.parse.quote("Autorización generada. La subida a SharePoint se procesará en segundo plano.")
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)

    except TemplateNotFoundError as e:
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as e:
        msg = urllib.parse.quote(f"Error generando autorización: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
