import sys
from pathlib import Path

# Agregar raíz del proyecto al sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import session_scope
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService


def main():
    print("--- Inicializador de Usuario Admin ---")
    username = input("Username [admin]: ").strip() or "admin"
    nombre = input("Nombre completo [Administrador]: ").strip() or "Administrador"
    password = input("Contraseña: ").strip()
    
    if not password:
        print("Error: La contraseña es obligatoria.")
        return

    telegram_id_str = input("Telegram Chat ID (opcional): ").strip()
    telegram_id = int(telegram_id_str) if telegram_id_str.isdigit() or (telegram_id_str.startswith("-") and telegram_id_str[1:].isdigit()) else None

    try:
        with session_scope() as db:
            existing = UserRepository.get_by_username(db, username)
            if existing:
                print(f"Error: El usuario '{username}' ya existe.")
                return
                
            user = User(
                username=username,
                nombre=nombre,
                hashed_password=AuthService.get_password_hash(password),
                telegram_id=telegram_id,
                role=UserRole.ADMIN,
                is_active=True
            )
            UserRepository.create(db, user)
            print(f"\n¡Éxito! Usuario '{username}' creado correctamente.")
            print(f"Ya puedes iniciar sesión en la plataforma Web con estas credenciales.")
    except Exception as e:
        print(f"Error al crear el usuario: {e}")

if __name__ == "__main__":
    main()
