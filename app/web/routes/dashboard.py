from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import get_db_session
from app.web.auth import get_current_user, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def get_web_db():
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)

    resumen = {
        "total": 12,
        "recibidos": 4,
        "en_revision": 3,
        "aprobados": 4,
        "rechazados": 1,
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "usuario": usuario,
            "resumen": resumen,
        }
    )
