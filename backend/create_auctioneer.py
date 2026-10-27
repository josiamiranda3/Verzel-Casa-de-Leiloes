
import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.wallet import Wallet


def main():
    name = input("Nome do leiloeiro: ").strip()
    email = input("E-mail do leiloeiro: ").strip().lower()
    password = getpass.getpass("Senha do leiloeiro: ")

    if len(name) < 2:
        print("Erro: informe um nome válido.")
        return

    if len(password) < 8:
        print("Erro: a senha deve ter pelo menos 8 caracteres.")
        return

    db = SessionLocal()

    try:
        existing_user = db.scalar(
            select(User).where(User.email == email)
        )

        if existing_user:
            print(
                "Erro: esse e-mail já está cadastrado. "
                "Nenhum usuário foi alterado."
            )
            return

        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=UserRole.AUCTIONEER,
        )

        db.add(user)
        db.flush()
        db.add(Wallet(user_id=user.id))
        db.commit()
        db.refresh(user)

        print("\nLeiloeiro criado com sucesso!")
        print(f"ID: {user.id}")
        print(f"Nome: {user.name}")
        print(f"E-mail: {user.email}")
        print(f"Perfil: {user.role.value}")

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
