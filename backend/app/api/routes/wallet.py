from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.audit_event import AuditEventType
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import TransactionType, WalletTransaction
from app.services.audit_service import record_event


router = APIRouter(prefix="/wallet", tags=["Carteira"])


class WalletDepositRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"), max_digits=14, decimal_places=2)


def _require_bidder(user: User) -> None:
    if user.role != UserRole.BIDDER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A carteira de depósitos e lances está disponível somente para arrematantes.",
        )


def _get_or_create_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.scalar(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    )
    if wallet is not None:
        return wallet

    # Compatibilidade com contas antigas que possam não ter carteira criada.
    wallet = Wallet(user_id=user_id)
    db.add(wallet)
    try:
        db.flush()
        return wallet
    except IntegrityError:
        # Outra requisição pode ter criado a carteira simultaneamente.
        db.rollback()
        wallet = db.scalar(select(Wallet).where(Wallet.user_id == user_id))
        if wallet is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Não foi possível inicializar a carteira. Tente novamente.",
            )
        return wallet


@router.get("/me")
def read_my_wallet(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retorna saldo total, comprometido e disponível do arrematante."""
    _require_bidder(current_user)
    wallet = _get_or_create_wallet(db, current_user.id)
    db.commit()
    db.refresh(wallet)
    available = wallet.balance - wallet.committed_balance
    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "balance": wallet.balance,
        "committed_balance": wallet.committed_balance,
        "available_balance": available,
    }


@router.get("/me/transactions")
def list_my_wallet_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista movimentações da carteira do arrematante autenticado."""
    _require_bidder(current_user)
    wallet = _get_or_create_wallet(db, current_user.id)
    db.commit()
    transactions = db.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet.id)
        .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
    ).all()

    result = []
    for transaction in transactions:
        if transaction.transaction_type in (TransactionType.DEPOSIT, TransactionType.BID_RELEASE, TransactionType.REFUND):
            direction = "credit" if transaction.transaction_type != TransactionType.BID_RELEASE else "release"
        elif transaction.transaction_type == TransactionType.BID_RESERVE:
            direction = "reserve"
        elif transaction.transaction_type == TransactionType.AUCTION_PAYMENT:
            direction = "debit" if (transaction.description or "").lower().startswith("pagamento") else "credit"
        else:
            direction = "—"
        result.append({
            "id": transaction.id,
            "wallet_id": transaction.wallet_id,
            "lot_id": transaction.lot_id,
            "transaction_type": transaction.transaction_type.value,
            "direction": direction,
            "amount": transaction.amount,
            "description": transaction.description,
            "created_at": transaction.created_at,
        })
    return result


@router.post("/deposit", status_code=status.HTTP_201_CREATED)
def deposit_to_my_wallet(
    data: WalletDepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Registra um depósito fictício para demonstração; não processa dinheiro real."""
    _require_bidder(current_user)
    amount = data.amount.quantize(Decimal("0.01"))
    wallet = _get_or_create_wallet(db, current_user.id)

    try:
        wallet.balance += amount
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.DEPOSIT,
            amount=amount,
            description="Depósito simulado de demonstração.",
        )
        db.add(transaction)
        db.flush()
        record_event(
            db,
            event_type=AuditEventType.WALLET_TRANSACTION,
            actor_user_id=current_user.id,
            entity_type="wallet",
            entity_id=wallet.id,
            description="Depósito simulado registrado na carteira do arrematante.",
            event_data={
                "transaction_type": TransactionType.DEPOSIT.value,
                "amount": format(amount, "f"),
                "simulated": True,
            },
            commit=False,
        )
        db.commit()
        db.refresh(wallet)
        db.refresh(transaction)
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Depósito simulado registrado.",
        "transaction_id": transaction.id,
        "amount": amount,
        "balance": wallet.balance,
        "committed_balance": wallet.committed_balance,
        "available_balance": wallet.balance - wallet.committed_balance,
    }
