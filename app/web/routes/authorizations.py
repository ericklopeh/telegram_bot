import urllib.parse

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.models.case import Case
from app.models.user import UserRole
from app.services.authorization_service import AuthorizationService, TemplateNotFoundError
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
        msg = urllib.parse.quote("Autorización y Orden SNTE generadas exitosamente.")
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)

    except TemplateNotFoundError as e:
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as e:
        msg = urllib.parse.quote(f"Error generando autorización: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
