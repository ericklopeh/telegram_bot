def calcular_revision_talon(
    percepciones: float,
    deducciones: float,
    extra: float = 0,
    tiene_programados: bool = False,
    monto_programados: float = 0,
) -> dict:
    percepciones = float(percepciones or 0)
    deducciones = float(deducciones or 0)
    extra = float(extra or 0)
    monto_programados = float(monto_programados or 0)

    total_70 = percepciones * 0.70
    saldo_70 = total_70 - deducciones
    programados = monto_programados if tiene_programados else 0
    liquidez_final = saldo_70 + extra - programados

    resultado = "Apto" if liquidez_final >= 0 else "No apto"

    return {
        "total_70": round(total_70, 2),
        "saldo_70": round(saldo_70, 2),
        "extra": round(extra, 2),
        "programados": round(programados, 2),
        "liquidez_final": round(liquidez_final, 2),
        "resultado": resultado,
    }