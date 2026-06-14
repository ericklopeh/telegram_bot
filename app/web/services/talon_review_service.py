from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.case import Case
from app.models.talon_review import TalonReview
from app.models.case_history import CaseHistory
from app.web.services.revision_talon_calculator import calcular_revision_talon


def guardar_revision_talon(
    db: Session,
    case: Case,
    percepciones: Decimal,
    deducciones: Decimal,
    liquido: Decimal,
    extra: Decimal,
    tiene_programados: bool,
    monto_programados: Decimal,
    usuario_nombre: str,
    source: str = "web",
    codigos_extraidos: dict | None = None,
    abono_extra: float = 0.0,
    programado: float = 0.0,
    cuentas_terminadas: list[dict] | None = None,
    mensaje: str | None = None,
) -> TalonReview:
    codigos = codigos_extraidos or {}
    cuentas = cuentas_terminadas or []

    # Use full calculator for consistency with Streamlit logic (enriched)
    revision = calcular_revision_talon(
        codigos_extraidos=codigos,
        descuentos_talon=float(deducciones or 0),
        abono_extra=float(abono_extra or extra or 0),
        programado=float(programado or monto_programados or 0),
        cuentas_terminadas=cuentas,
    )

    # Still compute basic fields for the model (no model changes yet)
    if not tiene_programados:
        monto_programados = Decimal("0.00")

    total_70 = percepciones * Decimal("0.70")
    saldo_70 = total_70 - deducciones
    liquidez_final = saldo_70 + extra - monto_programados

    resultado = "APTO" if liquidez_final > 0 else "NO APTO"

    review = TalonReview(
        case_id=case.id,
        percepciones=percepciones,
        deducciones=deducciones,
        liquido=liquido,
        extra=extra,
        tiene_programados=tiene_programados,
        monto_programados=monto_programados,
        total_70=total_70,
        saldo_70=saldo_70,
        liquidez_final=liquidez_final,
        resultado=resultado,
        source=source,
    )

    db.add(review)

    notes = f"Revisión de talón calculada manualmente en web: {resultado} (Liquidez final: ${liquidez_final:,.2f})"
    if mensaje:
        notes += f" | Mensaje: {mensaje[:200]}..."

    history_entry = CaseHistory(
        case_id=case.id,
        old_status=case.current_status,
        new_status=case.current_status,
        action_source=source,
        action_user=usuario_nombre,
        notes=notes,
    )

    db.add(history_entry)
    db.commit()
    db.refresh(review)

    return review
