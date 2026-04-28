import sys
from pathlib import Path

# Agrega la raíz del proyecto al path para poder importar app.*
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.db.session import session_scope
from app.domain.constants import (
    CASE_TYPE_PEDIDO,
    ORDER_TYPE_MUEBLE,
    ST_PED_RECIBIDO,
    VISIBLE_RECIBIDO,
)
from app.models.case import Case


def main():
    with session_scope() as db:
        exists = db.query(Case).filter(Case.public_id == "PED-DEMO-0001").first()

        if exists:
            print("El caso demo ya existe.")
            return

        folder = Path("storage") / "pedidos" / "SEM 17-2026" / "PED-DEMO-0001 CLIENTE DEMO"

        case = Case(
            public_id="PED-DEMO-0001",
            case_type=CASE_TYPE_PEDIDO,
            order_type=ORDER_TYPE_MUEBLE,
            client_name="CLIENTE DEMO SISTEMA",
            temp_folio="TMP-DEMO-0001",
            official_folio=None,
            current_status=ST_PED_RECIBIDO,
            visible_status=VISIBLE_RECIBIDO,
            seller_name="Vendedor Demo",
            seller_telegram_chat_id=None,
            week_code="SEM 17-2026",
            folder_path=str(folder),
        )

        db.add(case)

    print("Caso demo creado correctamente.")


if __name__ == "__main__":
    main()