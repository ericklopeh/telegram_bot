"""
Crea en la BD los usuarios listados en app/web/templates/login.html (demo web).

Uso (Docker, misma red que Postgres):
  docker compose exec web python scripts/seed_web_demo_users.py

Opcional: volver a fijar las contraseñas demo aunque el usuario ya exista:
  docker compose exec web python scripts/seed_web_demo_users.py --reset-passwords

En el host (con DATABASE_URL apuntando a localhost:5433 o similar):
  python scripts/seed_web_demo_users.py
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import session_scope
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService


@dataclass(frozen=True)
class _Demo:
    username: str
    password: str
    nombre: str
    role: UserRole


_DEMOS: tuple[_Demo, ...] = (
    _Demo("admin", "Admin2026!", "Administrador", UserRole.ADMIN),
    _Demo("jefe", "Jefe2026!", "Jefe de compras", UserRole.COMPRAS),
    _Demo("autorizaciones", "Auto2026!", "Autorizaciones SNTE", UserRole.AUTORIZACION),
    _Demo("vendedor", "Vend2026!", "Vendedor demo", UserRole.VENDEDOR),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Semilla usuarios web demo (login.html).")
    parser.add_argument(
        "--reset-passwords",
        action="store_true",
        help="Actualiza la contraseña hasheada de los usuarios demo si ya existían.",
    )
    args = parser.parse_args()

    created = 0
    updated = 0
    skipped = 0

    with session_scope() as db:
        for spec in _DEMOS:
            existing = UserRepository.get_by_username(db, spec.username)
            if existing is None:
                db.add(
                    User(
                        username=spec.username,
                        nombre=spec.nombre,
                        hashed_password=AuthService.get_password_hash(spec.password),
                        telegram_id=None,
                        role=spec.role,
                        is_active=True,
                    )
                )
                created += 1
            elif args.reset_passwords:
                existing.hashed_password = AuthService.get_password_hash(spec.password)
                existing.nombre = spec.nombre
                existing.role = spec.role
                existing.is_active = True
                updated += 1
            else:
                skipped += 1

    print(
        f"Listo. Creados={created}, contraseñas actualizadas={updated}, "
        f"ya existían (omitidos)={skipped}."
    )
    if skipped and not args.reset_passwords and skipped == len(_DEMOS):
        print(
            "Todos los usuarios demo ya existían. Si la contraseña no coincide, "
            "vuelve a ejecutar con --reset-passwords."
        )


if __name__ == "__main__":
    main()
