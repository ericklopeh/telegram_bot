from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Telegram Bot API", version="0.1.0")


class GenerarAutorizacionRequest(BaseModel):
    case_id: int = Field(..., description="ID interno del caso en base de datos")
    usuario: str | None = Field(default=None, description="Usuario que solicita la autorización")
    observaciones: str | None = Field(default=None, description="Notas opcionales para la autorización")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generar-autorizacion")
def generar_autorizacion(payload: GenerarAutorizacionRequest) -> dict[str, object]:
    """
    Endpoint base para integración con n8n.
    En un siguiente paso se conecta con `authorization_service`.
    """
    return {
        "ok": True,
        "mensaje": "Solicitud recibida",
        "case_id": payload.case_id,
        "usuario": payload.usuario,
        "observaciones": payload.observaciones,
    }
