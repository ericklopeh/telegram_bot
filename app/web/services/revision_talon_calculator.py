def obtener_importe(codigos: dict, codigo: str, equivalencias: list[str] = None) -> float:
    """
    Busca un código en el diccionario de códigos extraídos.
    También permite buscar equivalencias.
    Ejemplo:
    Q puede venir como A2
    7 puede venir como 07
    O1 puede venir como 01
    """
    equivalencias = equivalencias or []
    posibles_codigos = [codigo] + equivalencias
    for posible in posibles_codigos:
        if posible in codigos:
            return float(codigos[posible]["importe"])
    return 0.0


def filtrar_codigos_revision(codigos_extraidos: dict) -> dict:
    """
    Devuelve solo los códigos que usa el formato de revisión.
    """
    codigos_revision = {
        "E4": obtener_importe(codigos_extraidos, "E4"),
        "E3": obtener_importe(codigos_extraidos, "E3"),
        "Q": obtener_importe(codigos_extraidos, "Q", ["A2"]),
        "CP": obtener_importe(codigos_extraidos, "CP"),
        "7": obtener_importe(codigos_extraidos, "7", ["07"]),
        "CT": obtener_importe(codigos_extraidos, "CT"),
        "7B": obtener_importe(codigos_extraidos, "7B"),
        "E9": obtener_importe(codigos_extraidos, "E9"),
        "SG": obtener_importe(codigos_extraidos, "SG"),
        "O1": obtener_importe(codigos_extraidos, "O1", ["01"]),
        "DC": obtener_importe(codigos_extraidos, "DC"),
    }
    return codigos_revision


def calcular_ingresos_revision(codigos_revision: dict) -> float:
    """
    Suma solo los códigos que forman los ingresos liquidables.
    E4 + E3 + Q + CP + 7 + CT + 7B + E9 + SG
    """
    codigos_ingresos = ["E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG"]
    total = sum(codigos_revision.get(codigo, 0) for codigo in codigos_ingresos)
    return round(total, 2)


def formato_moneda(valor: float) -> str:
    if valor < 0:
        return f"-${abs(valor):,.2f}"
    return f"${valor:,.2f}"


def lineas_cuentas_para_mensaje(cuentas: list) -> list[str]:
    lineas = []
    for cuenta in cuentas:
        qna = str(cuenta.get("qna_termina", "")).strip() or "Sin QNA"
        monto = float(cuenta.get("saldo_liberado", 0) or 0)
        observacion = str(cuenta.get("observacion", "")).strip()
        linea = f"- QNA {qna}: {formato_moneda(monto)}"
        if observacion:
            linea += f" ({observacion})"
        lineas.append(linea)
    return lineas


def generar_resultado_liquidez(revision: dict, tiene_programado: str) -> str:
    liquidez_final = revision["liquidez_final"]
    programado = revision["programado"]
    cuentas_terminadas = revision.get("cuentas_terminadas", [])

    if cuentas_terminadas:
        if (
            revision.get("liquidez_talon", 0) < 0
            and revision.get("liquidez_antes_liberacion", 0) < 0
            and liquidez_final > 0
            and revision.get("total_saldo_liberado", 0) > 0
        ):
            resultado = (
                "Tenía sobregiro, pero queda con liquidez por cuentas terminadas: "
                f"{formato_moneda(liquidez_final)}."
            )
        elif liquidez_final > 0:
            resultado = f"Tiene liquidez disponible de {formato_moneda(liquidez_final)}."
        elif liquidez_final < 0:
            resultado = f"No tiene liquidez. Sobregiro final de {formato_moneda(liquidez_final)}."
        else:
            resultado = "Queda sin liquidez disponible ni sobregiro."

        if tiene_programado == "Sí" and programado > 0:
            resultado += f" Tiene un programado por {formato_moneda(programado)}."

        return resultado

    if liquidez_final > 0:
        if tiene_programado == "Sí" and programado > 0:
            return f"Tiene liquidez de {formato_moneda(liquidez_final)}. Tiene un programado por {formato_moneda(programado)}."
        return f"Tiene liquidez de {formato_moneda(liquidez_final)}."

    if liquidez_final < 0 and tiene_programado == "Sí" and programado > 0:
        return (
            f"No tiene liquidez. Tiene un sobregiro de: {formato_moneda(liquidez_final)}. "
            f"Tiene un programado por {formato_moneda(programado)}."
        )

    if liquidez_final < 0:
        return f"No tiene liquidez. Tiene un sobregiro de: {formato_moneda(liquidez_final)}."

    return "No tiene liquidez disponible."


def generar_mensaje_vendedor(datos: dict, revision: dict, tiene_programado: str) -> str:
    nombre = datos.get("nombre", "")
    rfc = datos.get("rfc", "")

    resultado_liquidez = generar_resultado_liquidez(revision=revision, tiene_programado=tiene_programado)
    cuentas = revision.get("cuentas_terminadas", [])

    if not cuentas:
        return f"""Se realizó la revisión del talón correspondiente al cliente:

Cliente: {nombre}
RFC: {rfc}

Resultado de la revisión:
{resultado_liquidez}"""

    cuentas_liberadas = [c for c in cuentas if c.get("sumar_a_liquidez", False)]
    cuentas_observadas = [c for c in cuentas if not c.get("sumar_a_liquidez", False)]
    liquidez_talon = revision.get("liquidez_talon", 0)
    estado_talon = (
        f"liquidez de {formato_moneda(liquidez_talon)}"
        if liquidez_talon >= 0
        else f"sobregiro de {formato_moneda(liquidez_talon)}"
    )
    bloques = [
        f"El cliente {nombre} presenta {estado_talon} en talón.",
        f"RFC: {rfc}"
    ]

    if cuentas_liberadas:
        bloques.append(
            "Adicionalmente, cuenta con saldos liberados por cuentas que terminan:\n"
            + "\n".join(lineas_cuentas_para_mensaje(cuentas_liberadas))
            + "\n\nTotal liberado: "
            + formato_moneda(revision.get("total_saldo_liberado", 0))
        )

    if cuentas_observadas:
        bloques.append(
            "Cuentas registradas solo como observación, sin sumar a liquidez:\n"
            + "\n".join(lineas_cuentas_para_mensaje(cuentas_observadas))
            + "\n\nTotal solo observado: "
            + formato_moneda(revision.get("total_solo_observado", 0))
        )

    bloques.append(f"Considerando lo anterior, {resultado_liquidez.lower()}")
    return "\n\n".join(bloques)


def calcular_revision_talon(
    codigos_extraidos: dict,
    descuentos_talon: float,
    abono_extra: float = 0,
    programado: float = 0,
    cuentas_terminadas: list[dict] = None,
) -> dict:
    """
    Lógica completa migrada de la calculadora de revisión de talones.
    """
    cuentas_terminadas = cuentas_terminadas or []
    codigos_revision = filtrar_codigos_revision(codigos_extraidos)

    ingresos = calcular_ingresos_revision(codigos_revision)

    saldo_100 = ingresos - descuentos_talon
    total_para_venta_70 = ingresos * 0.70
    saldo_70 = total_para_venta_70 - descuentos_talon

    saldo_mas_abonos_70 = saldo_70 - programado
    saldo_mas_abono_100 = saldo_100 - programado

    total_saldo_liberado = sum(
        float(cuenta.get("saldo_liberado", 0) or 0)
        for cuenta in cuentas_terminadas
        if cuenta.get("sumar_a_liquidez", False)
    )
    total_solo_observado = sum(
        float(cuenta.get("saldo_liberado", 0) or 0)
        for cuenta in cuentas_terminadas
        if not cuenta.get("sumar_a_liquidez", False)
    )

    liquidez_talon = saldo_100
    liquidez_antes_liberacion = liquidez_talon + abono_extra - programado
    liquidez_final = liquidez_antes_liberacion + total_saldo_liberado

    return {
        "codigos_revision": codigos_revision,
        "ingresos": round(ingresos, 2),
        "descuentos": round(descuentos_talon, 2),
        "saldo_100": round(saldo_100, 2),
        "total_para_venta_70": round(total_para_venta_70, 2),
        "saldo_70": round(saldo_70, 2),
        "saldo_mas_abonos_70": round(saldo_mas_abonos_70, 2),
        "saldo_mas_abono_100": round(saldo_mas_abono_100, 2),
        "abono_extra": round(abono_extra, 2),
        "programado": round(programado, 2),
        "cuentas_terminadas": cuentas_terminadas,
        "liquidez_talon": round(liquidez_talon, 2),
        "total_saldo_liberado": round(total_saldo_liberado, 2),
        "total_solo_observado": round(total_solo_observado, 2),
        "liquidez_antes_liberacion": round(liquidez_antes_liberacion, 2),
        "liquidez_final": round(liquidez_final, 2),
    }