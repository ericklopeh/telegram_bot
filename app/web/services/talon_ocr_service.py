import os
import re
import traceback
from PIL import Image
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.ocr_result import OcrResult

try:
    import pytesseract
except ImportError:
    pytesseract = None

TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if pytesseract is not None and TESSERACT_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)

def extract_talon_fields(raw_text: str) -> dict:
    """
    Extrae heurísticamente los campos de percepciones, deducciones y líquido
    a partir del texto crudo (OCR) tolerando símbolos de moneda, espacios y comas.
    Prioriza las etiquetas exactas de los talones de nómina reales e incluye
    extracción de conceptos por código.
    """
    number_pattern = r'[:=\-\s\$]*([\d,]+(?:\.\d{1,2})?)'
    
    def parse_number(match):
        if match:
            try:
                return float(match.group(1).replace(',', ''))
            except ValueError:
                return None
        return None

    def search_with_priority(patterns, text):
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match
        return None

    percepciones_total = None
    deducciones_total = None
    liquido = None

    # 1. Búsqueda de alta prioridad: Patrón tabular exacto del talón
    tabular_header_match = re.search(r'(?i)PERCEPCIONES\s+DESCUENTOS\s+L[IÍ]QUIDO', raw_text)
    if tabular_header_match:
        text_after_header = raw_text[tabular_header_match.end():tabular_header_match.end() + 300]
        # Eliminar fechas para evitar confundirlas con importes (ej. 14/04/2026)
        text_no_dates = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', text_after_header)
        # Buscar 3 importes seguidos
        amounts_match = re.search(r'([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})', text_no_dates)
        
        if amounts_match:
            try:
                percepciones_total = float(amounts_match.group(1).replace(',', ''))
                deducciones_total = float(amounts_match.group(2).replace(',', ''))
                liquido = float(amounts_match.group(3).replace(',', ''))
            except ValueError:
                pass

    # 2. Búsqueda de prioridad por etiquetas (fallback)
    if percepciones_total is None or deducciones_total is None or liquido is None:
        percepciones_patterns = [
            r'(?i)total\s+de\s+percepciones\s+y\s+otros\s+pagos' + number_pattern,
            r'(?i)total\s+percepciones' + number_pattern,
            r'(?i)percepciones\s+y\s+otros\s+pagos' + number_pattern,
            r'(?i)percepci[oó]n(?:es)?' + number_pattern
        ]
        
        deducciones_patterns = [
            r'(?i)total\s+de\s+deducciones' + number_pattern,
            r'(?i)total\s+deducciones' + number_pattern,
            r'(?i)deducci[oó]n(?:es)?' + number_pattern,
            r'(?i)descuentos?' + number_pattern
        ]
        
        liquido_patterns = [
            r'(?i)total\s+pagado' + number_pattern,
            r'(?i)neto\s+pagado' + number_pattern,
            r'(?i)(?:l[íi]quido|neto)' + number_pattern
        ]

        p_percepciones = search_with_priority(percepciones_patterns, raw_text)
        p_deducciones = search_with_priority(deducciones_patterns, raw_text)
        p_liquido = search_with_priority(liquido_patterns, raw_text)
        
        percepciones_total = percepciones_total or parse_number(p_percepciones)
        deducciones_total = deducciones_total or parse_number(p_deducciones)
        liquido = liquido or parse_number(p_liquido)

    # Buscar conceptos por línea
    line_item_pattern = r'^\s*([A-Z0-9]{2,3})\s+([A-Za-z0-9\s\.\-\/\,]+?)\s+([\d,]+\.\d{2})\s*$'
    income_items = []
    deduction_items = []
    
    capacity_keys = ["E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG", "O1", "D", "DC"]
    capacity_codes = {k: 0.0 for k in capacity_keys}
    
    # Heurística para separar deducciones: buscar la palabra DESCUENTOS o DEDUCCIONES
    desc_idx = raw_text.upper().find("DESCUENTOS")
    if desc_idx == -1:
        desc_idx = raw_text.upper().find("DEDUCCIONES")
        
    for match in re.finditer(line_item_pattern, raw_text, re.MULTILINE):
        raw_code = match.group(1).strip()
        desc = match.group(2).strip()
        try:
            amt = float(match.group(3).replace(',', ''))
        except:
            amt = 0.0
            
        # Normalización
        code = raw_code
        if code == "Q1": code = "Q"
        if code == "07": code = "7"
        if code == "01" or code == "O1": code = "O1"
        
        item = {"code": raw_code, "description": desc, "amount": amt}
        
        if desc_idx != -1 and match.start() > desc_idx:
            deduction_items.append(item)
        else:
            income_items.append(item)
            
        if code in capacity_keys:
            capacity_codes[code] = amt

    # Regla: D debe ser deducciones_total
    capacity_codes["D"] = deducciones_total or 0.0
    
    # Construir review_fields
    review_fields = {
        "E4": capacity_codes.get("E4", 0.0),
        "E3": capacity_codes.get("E3", 0.0),
        "Q": capacity_codes.get("Q", 0.0),
        "CP": capacity_codes.get("CP", 0.0),
        "7": capacity_codes.get("7", 0.0),
        "CT": capacity_codes.get("CT", 0.0),
        "7B": capacity_codes.get("7B", 0.0),
        "E9": capacity_codes.get("E9", 0.0),
        "SG": capacity_codes.get("SG", 0.0),
        "O1": capacity_codes.get("O1", 0.0),
        "D": deducciones_total or 0.0,
        "DC": 0.0
    }
    
    # Cálculos
    income_keys = ["E4", "E3", "Q", "CP", "7", "CT", "7B", "E9", "SG", "O1"]
    capacity_income_total = sum(capacity_codes.get(k, 0.0) for k in income_keys)
    saldo = capacity_income_total - capacity_codes["D"]
    total_para_venta_70 = capacity_income_total * 0.70
    saldo_al_70 = total_para_venta_70 - capacity_codes["D"]
        
    return {
        "percepciones_total": percepciones_total,
        "deducciones_total": deducciones_total,
        "liquido": liquido,
        "income_items": income_items,
        "deduction_items": deduction_items,
        "capacity_codes": capacity_codes,
        "review_fields": review_fields,
        "capacity_income_total": capacity_income_total,
        "saldo": saldo,
        "total_para_venta_70": total_para_venta_70,
        "saldo_al_70": saldo_al_70
    }

def process_ocr_document(db: Session, document_id: int, action_user: str | None = "web") -> OcrResult | None:
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        return None
        
    ocr_result = OcrResult(
        document_id=document_id,
        raw_text=None,
        parsed_json={},
        confidence_score=None,
        review_status="pending"
    )
    db.add(ocr_result)
    
    try:
        if pytesseract is None:
            raise RuntimeError(
                "pytesseract no esta instalado. Instala pytesseract y Tesseract OCR para procesar documentos."
            )

        if not document.file_path or not os.path.exists(document.file_path):
            raise FileNotFoundError(f"El archivo {document.file_path} no existe en disco.")
            
        ext = os.path.splitext(document.file_path)[1].lower()
        
        if ext == '.pdf':
            import fitz
            doc_pdf = fitz.open(document.file_path)
            if len(doc_pdf) == 0:
                doc_pdf.close()
                raise ValueError("El documento PDF está vacío o no tiene páginas.")
                
            page = doc_pdf[0]
            # Render con zoom 2x para mejor calidad de OCR
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            
            # Convertir Pixmap a PIL Image
            if pix.alpha:
                image = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples).convert("RGB")
            else:
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc_pdf.close()
        else:
            # Try to open as image
            image = Image.open(document.file_path)
            
        # Execute OCR
        # We use lang="spa" if installed, else fallback.
        try:
            raw_text = pytesseract.image_to_string(image, lang="spa")
        except pytesseract.TesseractError:
            raw_text = pytesseract.image_to_string(image) # fallback to default (usually eng)
            
        # Extraer campos usando la nueva función
        extracted_fields = extract_talon_fields(raw_text)
        
        parsed_data = {
            "status": "processed",
            "message": "OCR completado exitosamente."
        }
        parsed_data.update(extracted_fields)
            
        ocr_result.raw_text = raw_text
        ocr_result.parsed_json = parsed_data
        ocr_result.review_status = "processed"
        
    except Exception as e:
        error_msg = str(e)
        if "tesseract is not installed" in error_msg.lower() or "not found" in error_msg.lower():
            error_msg = "Tesseract OCR no está instalado en el sistema o no está en el PATH."
            
        ocr_result.review_status = "error"
        ocr_result.parsed_json = {
            "status": "error",
            "message": "Fallo al procesar OCR",
            "error_detail": error_msg
        }
        ocr_result.raw_text = f"ERROR: {error_msg}"
        
    db.commit()
    db.refresh(ocr_result)
    
    return ocr_result
