"""
pdf_orden_service.py
========================
Genera una Orden de Descuento SNTE Sección 21 llenando la plantilla PDF
con los datos del agremiado.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------------------------------------------------------------------------
# Registro de fuentes
# ---------------------------------------------------------------------------

def _register_fonts() -> tuple[str, str]:
    r"""
    Devuelve (nombre_regular, nombre_bold).
    Busca en storage/fonts/, luego intenta Cambria (Windows) -> Carlito (Linux) -> Helvetica (fallback).
    """
    fonts_dir = Path("storage/fonts")
    cambria_reg_local = fonts_dir / "cambria.ttf"
    cambria_bold_local = fonts_dir / "cambrib.ttf"

    if cambria_reg_local.exists() and cambria_bold_local.exists():
        try:
            pdfmetrics.registerFont(TTFont("Cambria", str(cambria_reg_local)))
            pdfmetrics.registerFont(TTFont("Cambria-Bold", str(cambria_bold_local)))
            return "Cambria", "Cambria-Bold"
        except Exception:
            pass

    cambria_reg_ttf = r"C:\Windows\Fonts\cambria.ttf"
    cambria_bold_ttf = r"C:\Windows\Fonts\cambrib.ttf"
    if os.path.exists(cambria_reg_ttf) and os.path.exists(cambria_bold_ttf):
        try:
            pdfmetrics.registerFont(TTFont("Cambria", cambria_reg_ttf))
            pdfmetrics.registerFont(TTFont("Cambria-Bold", cambria_bold_ttf))
            return "Cambria", "Cambria-Bold"
        except Exception:
            pass

    cambria_paths = [
        r"C:\Windows\Fonts\cambria.ttc",
        r"C:\Windows\Fonts\Cambria.ttc",
    ]
    for path in cambria_paths:
        if os.path.exists(path):
            for bold_idx in (2, 1):
                try:
                    pdfmetrics.registerFont(TTFont("Cambria", path, subfontIndex=0))
                    pdfmetrics.registerFont(TTFont("Cambria-Bold", path, subfontIndex=bold_idx))
                    return "Cambria", "Cambria-Bold"
                except Exception:
                    continue

    carlito_reg = "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"
    carlito_bold = "/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"
    if os.path.exists(carlito_reg) and os.path.exists(carlito_bold):
        pdfmetrics.registerFont(TTFont("Carlito", carlito_reg))
        pdfmetrics.registerFont(TTFont("Carlito-Bold", carlito_bold))
        return "Carlito", "Carlito-Bold"

    print("[warn] Cambria/Carlito no disponibles, usando Helvetica.")
    return "Helvetica", "Helvetica-Bold"


# ---------------------------------------------------------------------------
# Geometría: coordenadas extraídas directamente del PDF de referencia
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = LETTER  # 612 x 792

FONT_TEXTO_SIZE = 7.5   # Cambria regular
FONT_MONTO_SIZE = 9.0   # Cambria-Bold
ASCENT_FACTOR = 0.75

CAMPOS_TEXTO: dict[str, list[tuple[float, float]]] = {
    "nombre":       [( 80.00,  92.62), ( 85.00, 370.67)],
    "rfc":          [( 64.00, 107.90), ( 69.00, 384.50)],
    "categoria":    [(225.00, 103.25), (230.00, 385.25)],
    "domicilio":    [( 87.00, 123.18), ( 92.00, 399.92)],
    "tel_part":     [( 85.00, 138.45), ( 90.00, 415.67)],
    "tel_celular":  [(206.00, 134.42), (211.00, 416.42)],
    "correo":       [(315.00, 133.67), (320.00, 415.67)],
    "fecha_venta":  [(349.66, 167.42), (346.80, 450.92)],
}

FIRMA_LINEA_1_TOP = [278.42, 561.17]
FIRMA_LINEA_2_TOP = [287.42, 570.17]
FIRMA_CENTRO_X = 124.0

CAMPOS_BOLD: dict[str, list[tuple[float, float]]] = {
    "qna_inicial":   [(179.25, 193.25), (177.00, 476.75)],
    "qna_final":     [(270.75, 193.25), (268.50, 476.75)],
    "descuento_qna": [( 69.96, 191.82), ( 69.96, 474.42)],
    "plazo_qnas":    [(381.08, 197.91), (381.08, 480.91)],
}

_MARGIN = 1.5
PLACEHOLDERS = [
    (349.66, 167.42, 28.12, 7.50),
    (179.25, 193.25, 29.69, 9.00),
    (270.75, 193.25, 34.59, 9.00),
    (381.08, 197.91, 10.66, 9.00),
    (346.80, 450.92, 40.58, 7.50),
    (177.00, 476.75, 29.69, 9.00),
    (268.50, 476.75, 34.59, 9.00),
    ( 78.00, 190.00, 30.00, 9.50),
    ( 75.75, 472.00, 30.00, 9.50),
    ( 65.00, 278.00, 120.00, 18.00),
    ( 63.00, 561.00, 120.00, 18.00),
]

CAMPO_FOLIO: list[tuple[float, float]] = [
    (400.0,  80.5),
    (400.0, 362.5),
]
FONT_FOLIO_SIZE = 8.0


@dataclass
class DatosOrden:
    nombre: str = ""
    rfc: str = ""
    categoria: str = ""
    domicilio: str = ""
    tel_part: str = ""
    tel_celular: str = ""
    correo: str = ""
    fecha_venta: str = ""
    qna_inicial: str = ""
    qna_final: str = ""
    descuento_qna: str = ""
    plazo_qnas: str = ""
    folio: str = ""


def _top_to_y(top: float, font_size: float) -> float:
    ascent = font_size * ASCENT_FACTOR
    return PAGE_H - (top + ascent)


def _draw_emphasis_text(c: canvas.Canvas, x: float, y: float, text: str, font_name: str, font_size: float) -> None:
    c.setFont(font_name, font_size)
    c.drawString(x, y, text)
    c.drawString(x + 0.22, y, text)


def _draw_overlay(datos: DatosOrden, font_reg: str, font_bold: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)

    c.setFillColorRGB(1, 1, 1)
    for (x, top, w, h) in PLACEHOLDERS:
        y_bottom = PAGE_H - (top + h) - _MARGIN
        c.rect(x - _MARGIN, y_bottom, w + 2 * _MARGIN, h + 2 * _MARGIN, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)

    c.setFont(font_reg, FONT_TEXTO_SIZE)
    for key, positions in CAMPOS_TEXTO.items():
        val = getattr(datos, key, "")
        if not val: continue
        for (x, top) in positions:
            y = _top_to_y(top, FONT_TEXTO_SIZE)
            c.drawString(x, y, str(val))

    if datos.nombre:
        linea1 = f"C. {datos.nombre}"
        linea2 = "AGREMIADO A LA SECC. 21 DEL SNTE"
        w1 = c.stringWidth(linea1, font_reg, FONT_TEXTO_SIZE)
        w2 = c.stringWidth(linea2, font_reg, FONT_TEXTO_SIZE)
        for i in range(2):
            x1 = FIRMA_CENTRO_X - w1 / 2
            x2 = FIRMA_CENTRO_X - w2 / 2
            c.drawString(x1, _top_to_y(FIRMA_LINEA_1_TOP[i], FONT_TEXTO_SIZE), linea1)
            c.drawString(x2, _top_to_y(FIRMA_LINEA_2_TOP[i], FONT_TEXTO_SIZE), linea2)

    c.setFont(font_bold, FONT_MONTO_SIZE)
    for key, positions in CAMPOS_BOLD.items():
        if key == "descuento_qna": continue
        val = getattr(datos, key, "")
        if not val: continue
        for (x, top) in positions:
            y = _top_to_y(top, FONT_MONTO_SIZE)
            _draw_emphasis_text(c, x, y, str(val), font_bold, FONT_MONTO_SIZE)
            text_width = c.stringWidth(str(val), font_bold, FONT_MONTO_SIZE)
            c.setLineWidth(0.5)
            c.line(x, y - 1.2, x + text_width, y - 1.2)

    if datos.descuento_qna:
        for (x_base, top) in CAMPOS_BOLD["descuento_qna"]:
            y = _top_to_y(top, FONT_MONTO_SIZE)
            _draw_emphasis_text(c, x_base - 8.0, y, "$", font_bold, FONT_MONTO_SIZE)
            _draw_emphasis_text(c, x_base, y, str(datos.descuento_qna), font_bold, FONT_MONTO_SIZE)
            monto_width = c.stringWidth(str(datos.descuento_qna), font_bold, FONT_MONTO_SIZE)
            c.setLineWidth(0.5)
            c.line(x_base, y - 1.2, x_base + monto_width, y - 1.2)
            c.setFont(font_reg, FONT_TEXTO_SIZE)
            c.drawString(x_base + monto_width + 2.0, _top_to_y(top + 1.64, FONT_TEXTO_SIZE), "PESOS")

    if datos.folio:
        c.setFont(font_bold, FONT_FOLIO_SIZE)
        for (x, top) in CAMPO_FOLIO:
            y = _top_to_y(top, FONT_FOLIO_SIZE)
            c.drawString(x, y, str(datos.folio))

    c.showPage()
    c.save()
    return buf.getvalue()


def generar_orden_snte_pdf(
    plantilla: str,
    salida: str,
    datos: dict | DatosOrden,
) -> str:
    """
    Genera la orden de descuento fusionando overlay sobre la plantilla.
    """
    if isinstance(datos, dict):
        datos = DatosOrden(**datos)

    font_reg, font_bold = _register_fonts()
    overlay_bytes = _draw_overlay(datos, font_reg, font_bold)

    base = PdfReader(plantilla)
    overlay = PdfReader(io.BytesIO(overlay_bytes))
    writer = PdfWriter()

    page = base.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    with open(salida, "wb") as f:
        writer.write(f)

    return salida
