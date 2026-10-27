
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, text

from app.core.security import create_access_token
from app.models.audit_event import AuditEvent, AuditEventType
from app.models.bid import Bid
from app.models.lot import Lot, LotStatus
from app.models.user import User, UserRole
from app.models.wallet import Wallet
from app.models.wallet_transaction import (
    TransactionType,
    WalletTransaction,
)
from app.services.audit_service import verify_audit_chain
from app.api.routes import bids


def test_real_api_bid_persists_financial_and_audit_records(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)


    auctioneer = User(
        name="Leiloeiro sem Token",
        email="leiloeiro.sem.token@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante sem Token",
        email="arrematante.sem.token@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )


    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )
    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote de Integração",
        description="Lote fictício para teste automatizado",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/bids/",
        json={"lot_id": lot.id, "amount": "100.00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text

    response_data = response.json()
    bid_id = response_data["id"]

    assert response_data["lot_id"] == lot.id
    assert response_data["bidder_id"] == bidder.id
    assert Decimal(response_data["amount"]) == Decimal("100.00")

    saved_bid = db_session.scalar(
        select(Bid).where(Bid.id == bid_id)
    )
    assert saved_bid is not None

    db_session.refresh(wallet)
    assert wallet.balance == Decimal("1000.00")
    assert wallet.committed_balance == Decimal("100.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet.id,
            WalletTransaction.lot_id == lot.id,
        )
    ).all()

    reserve_transactions = [
        transaction
        for transaction in transactions
        if transaction.transaction_type == TransactionType.BID_RESERVE
    ]

    assert len(reserve_transactions) == 1
    assert reserve_transactions[0].amount == Decimal("100.00")

    events = db_session.scalars(
        select(AuditEvent).order_by(AuditEvent.id.asc())
    ).all()

    event_types = {event.event_type for event in events}
    assert AuditEventType.BID_PLACED in event_types
    assert AuditEventType.WALLET_TRANSACTION in event_types

    chain_result = verify_audit_chain(db_session)
    assert chain_result["valid"] is True, chain_result


def test_new_leader_releases_previous_bidder_reservation(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro Disputa",
        email="leiloeiro.disputa@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    first_bidder = User(
        name="Primeiro Arrematante",
        email="primeiro.disputa@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )
    second_bidder = User(
        name="Segundo Arrematante",
        email="segundo.disputa@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, first_bidder, second_bidder])
    db_session.flush()

    first_wallet = Wallet(
        user_id=first_bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )
    second_wallet = Wallet(
        user_id=second_bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )
    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote de Disputa de Integração",
        description="Teste da troca de líder",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([first_wallet, second_wallet, lot])
    db_session.flush()

    first_token = create_access_token(subject=str(first_bidder.id))
    first_response = client.post(
        "/bids/",
        json={"lot_id": lot.id, "amount": "100.00"},
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert first_response.status_code == 201, first_response.text

    db_session.refresh(first_wallet)
    assert first_wallet.balance == Decimal("1000.00")
    assert first_wallet.committed_balance == Decimal("100.00")

    second_token = create_access_token(subject=str(second_bidder.id))
    second_response = client.post(
        "/bids/",
        json={"lot_id": lot.id, "amount": "110.00"},
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert second_response.status_code == 201, second_response.text

    db_session.refresh(first_wallet)
    db_session.refresh(second_wallet)

    assert first_wallet.balance == Decimal("1000.00")
    assert first_wallet.committed_balance == Decimal("0.00")
    assert second_wallet.balance == Decimal("1000.00")
    assert second_wallet.committed_balance == Decimal("110.00")

    bids = db_session.scalars(
        select(Bid)
        .where(Bid.lot_id == lot.id)
        .order_by(Bid.amount.asc())
    ).all()

    assert len(bids) == 2
    assert bids[0].bidder_id == first_bidder.id
    assert bids[0].amount == Decimal("100.00")
    assert bids[1].bidder_id == second_bidder.id
    assert bids[1].amount == Decimal("110.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id
        )
    ).all()

    assert any(
        transaction.wallet_id == first_wallet.id
        and transaction.transaction_type == TransactionType.BID_RESERVE
        and transaction.amount == Decimal("100.00")
        for transaction in transactions
    )
    assert any(
        transaction.wallet_id == first_wallet.id
        and transaction.transaction_type == TransactionType.BID_RELEASE
        and transaction.amount == Decimal("100.00")
        for transaction in transactions
    )
    assert any(
        transaction.wallet_id == second_wallet.id
        and transaction.transaction_type == TransactionType.BID_RESERVE
        and transaction.amount == Decimal("110.00")
        for transaction in transactions
    )

    events = db_session.scalars(
        select(AuditEvent).order_by(AuditEvent.id.asc())
    ).all()

    event_types = {event.event_type for event in events}
    assert AuditEventType.BID_PLACED in event_types
    assert AuditEventType.WALLET_TRANSACTION in event_types

    chain_result = verify_audit_chain(db_session)
    assert chain_result["valid"] is True, chain_result


def test_audit_failure_rolls_back_real_bid_and_reservation(
    isolated_client,
    independent_engine,
):
    now = datetime.now(timezone.utc)

    # Confirma os dados de preparação em uma transação independente.
    with Session(
        bind=independent_engine,
        autoflush=False,
        expire_on_commit=False,
    ) as setup_session:
        auctioneer = User(
            name="Leiloeiro Rollback",
            email="leiloeiro.rollback@example.test",
            password_hash="hash-ficticio-apenas-para-teste",
            role=UserRole.AUCTIONEER,
        )
        bidder = User(
            name="Arrematante Rollback",
            email="arrematante.rollback@example.test",
            password_hash="hash-ficticio-apenas-para-teste",
            role=UserRole.BIDDER,
        )

        setup_session.add_all([auctioneer, bidder])
        setup_session.flush()

        wallet = Wallet(
            user_id=bidder.id,
            balance=Decimal("1000.00"),
            committed_balance=Decimal("0.00"),
        )
        lot = Lot(
            auctioneer_id=auctioneer.id,
            title="Lote para teste de rollback",
            description="Teste de reversão transacional",
            initial_bid=Decimal("100.00"),
            minimum_increment=Decimal("10.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=1),
            status=LotStatus.LIVE,
        )

        setup_session.add_all([wallet, lot])
        setup_session.flush()

        wallet_id = wallet.id
        lot_id = lot.id
        bidder_id = bidder.id
        auctioneer_id = auctioneer.id

        setup_session.commit()

    token = create_access_token(subject=str(bidder_id))

    def fail_on_bid_placed(db, **kwargs):
        if kwargs.get("event_type") == AuditEventType.BID_PLACED:
            raise RuntimeError("Falha simulada na auditoria do lance")

        from app.services.audit_service import record_event

        return record_event(db, **kwargs)

    try:
        with patch(
            "app.api.routes.bids.record_event",
            side_effect=fail_on_bid_placed,
        ):
            with pytest.raises(
                RuntimeError,
                match="Falha simulada na auditoria do lance",
            ):
                isolated_client.post(
                    "/bids/",
                    json={"lot_id": lot_id, "amount": "100.00"},
                    headers={"Authorization": f"Bearer {token}"},
                )

        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as verification_session:
            saved_bids = verification_session.scalars(
                select(Bid).where(Bid.lot_id == lot_id)
            ).all()
            assert saved_bids == []

            saved_wallet = verification_session.get(Wallet, wallet_id)
            assert saved_wallet is not None
            assert saved_wallet.balance == Decimal("1000.00")
            assert saved_wallet.committed_balance == Decimal("0.00")

            saved_transactions = verification_session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.lot_id == lot_id,
                )
            ).all()
            assert saved_transactions == []

            saved_lot = verification_session.get(Lot, lot_id)
            assert saved_lot is not None
            assert saved_lot.status == LotStatus.LIVE

    finally:
        # Limpa somente os registros associados a este cenário.
        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as cleanup_session:
            cleanup_session.query(WalletTransaction).filter(
                WalletTransaction.lot_id == lot_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Bid).filter(
                Bid.lot_id == lot_id
            ).delete(synchronize_session=False)

            # Não apagamos eventos da cadeia global de auditoria:
            # isso poderia invalidar os hashes dos eventos posteriores.
            cleanup_session.query(Wallet).filter(
                Wallet.id == wallet_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Lot).filter(
                Lot.id == lot_id
            ).delete(synchronize_session=False)

            cleanup_session.query(User).filter(
                User.id.in_([bidder_id, auctioneer_id])
            ).delete(synchronize_session=False)

            cleanup_session.commit()

def test_bid_is_rejected_if_lot_expires_while_waiting_for_lock(
    isolated_client,
    independent_engine,
):
    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(seconds=2)

    # Cria os dados e confirma a transação de preparação.
    with Session(
        bind=independent_engine,
        autoflush=False,
        expire_on_commit=False,
    ) as setup_session:
        auctioneer = User(
            name="Leiloeiro Concorrência",
            email="leiloeiro.concorrencia@example.test",
            password_hash="hash-de-teste",
            role=UserRole.AUCTIONEER,
        )
        bidder = User(
            name="Arrematante Concorrência",
            email="arrematante.concorrencia@example.test",
            password_hash="hash-de-teste",
            role=UserRole.BIDDER,
        )

        setup_session.add_all([auctioneer, bidder])
        setup_session.flush()

        wallet = Wallet(
            user_id=bidder.id,
            balance=Decimal("1000.00"),
            committed_balance=Decimal("0.00"),
        )

        lot = Lot(
            auctioneer_id=auctioneer.id,
            title="Lote para teste de concorrência",
            description="Teste de expiração durante bloqueio",
            initial_bid=Decimal("100.00"),
            minimum_increment=Decimal("10.00"),
            starts_at=now - timedelta(hours=1),
            ends_at=ends_at,
            status=LotStatus.LIVE,
        )

        setup_session.add_all([wallet, lot])
        setup_session.flush()

        bidder_id = bidder.id
        auctioneer_id = auctioneer.id
        wallet_id = wallet.id
        lot_id = lot.id

        setup_session.commit()

    token = create_access_token(subject=str(bidder_id))

    lock_session = Session(
        bind=independent_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    executor = ThreadPoolExecutor(max_workers=1)
    future = None

    try:
        # Mantém o bloqueio da linha do lote nesta transação.
        locked_lot = lock_session.scalar(
            select(Lot)
            .where(Lot.id == lot_id)
            .with_for_update()
        )
        assert locked_lot is not None

        # A requisição usará outra sessão e deverá esperar pelo bloqueio.
        with patch("app.api.routes.bids.record_event"):
            future = executor.submit(
                isolated_client.post,
                "/bids/",
                json={
                    "lot_id": lot_id,
                    "amount": "100.00",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

            # Espera até que o PostgreSQL confirme a espera por um lock.
            deadline = time.monotonic() + 5
            waiting_for_lock = False

            while time.monotonic() < deadline:
                with independent_engine.connect() as monitor_connection:
                    waiting_for_lock = monitor_connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_stat_activity
                                WHERE datname = current_database()
                                  AND pid <> pg_backend_pid()
                                  AND wait_event_type = 'Lock'
                                  AND query ILIKE '%FOR UPDATE%'
                            )
                            """
                        )
                    ).scalar_one()

                if waiting_for_lock:
                    break

                time.sleep(0.05)

            assert waiting_for_lock, (
                "A requisição não foi observada aguardando o bloqueio "
                "do lote no PostgreSQL."
            )

            # Mantém o bloqueio até que o prazo do lote tenha terminado.
            remaining = (
                ends_at - datetime.now(timezone.utc)
            ).total_seconds()

            if remaining > 0:
                time.sleep(remaining + 0.2)

    finally:
        # Libera o lote mesmo se uma asserção falhar.
        lock_session.rollback()
        lock_session.close()

        executor.shutdown(wait=True)

    try:
        assert future is not None
        response = future.result(timeout=5)

        assert response.status_code == 409, (
            "Um lance não deve ser aceito depois que o lote expira. "
            f"Resposta recebida: {response.status_code} - {response.text}"
        )
        assert response.json()["detail"] == (
            "O prazo para lances deste lote terminou."
        )

    finally:
        # Limpa somente os registros deste teste.
        # A auditoria foi simulada para não modificar a cadeia global.
        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as cleanup_session:
            cleanup_session.query(WalletTransaction).filter(
                WalletTransaction.lot_id == lot_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Bid).filter(
                Bid.lot_id == lot_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Wallet).filter(
                Wallet.id == wallet_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Lot).filter(
                Lot.id == lot_id
            ).delete(synchronize_session=False)

            cleanup_session.query(User).filter(
                User.id.in_([bidder_id, auctioneer_id])
            ).delete(synchronize_session=False)

            cleanup_session.commit()



def test_concurrent_bids_keep_wallet_reservations_consistent(
    isolated_client,
    independent_engine,
):
    """Dois lances concorrentes devem manter reservas consistentes."""
    now = datetime.now(timezone.utc)

    with Session(
        bind=independent_engine,
        autoflush=False,
        expire_on_commit=False,
    ) as setup_session:
        auctioneer = User(
            name="Leiloeiro Concorrência Financeira",
            email="leiloeiro.concorrencia.financeira@example.test",
            password_hash="hash-ficticio-apenas-para-teste",
            role=UserRole.AUCTIONEER,
        )
        bidders = [
            User(
                name="Arrematante Concorrente A",
                email="concorrente.a@example.test",
                password_hash="hash-ficticio-apenas-para-teste",
                role=UserRole.BIDDER,
            ),
            User(
                name="Arrematante Concorrente B",
                email="concorrente.b@example.test",
                password_hash="hash-ficticio-apenas-para-teste",
                role=UserRole.BIDDER,
            ),
        ]
        setup_session.add_all([auctioneer, *bidders])
        setup_session.flush()

        wallets = [
            Wallet(
                user_id=bidder.id,
                balance=Decimal("1000.00"),
                committed_balance=Decimal("0.00"),
            )
            for bidder in bidders
        ]
        lot = Lot(
            auctioneer_id=auctioneer.id,
            title="Lote de Concorrência Financeira",
            description="Teste automatizado de lances concorrentes",
            initial_bid=Decimal("100.00"),
            minimum_increment=Decimal("10.00"),
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1),
            status=LotStatus.LIVE,
        )
        setup_session.add_all([*wallets, lot])
        setup_session.flush()

        auctioneer_id = auctioneer.id
        bidder_ids = [bidder.id for bidder in bidders]
        wallet_ids = [wallet.id for wallet in wallets]
        lot_id = lot.id
        tokens = [
            create_access_token(subject=str(bidder.id))
            for bidder in bidders
        ]
        setup_session.commit()

    responses = []

    try:
        # Cada requisição é atendida por uma sessão de banco independente.
        def submit_bid(index, amount):
            return isolated_client.post(
                "/bids/",
                json={"lot_id": lot_id, "amount": amount},
                headers={"Authorization": f"Bearer {tokens[index]}"},
            )

        with patch("app.api.routes.bids.record_event"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(submit_bid, 0, "100.00"),
                    executor.submit(submit_bid, 1, "110.00"),
                ]
                responses = [future.result(timeout=15) for future in futures]

        assert all(response.status_code in (201, 409, 422) for response in responses), [
            (response.status_code, response.text)
            for response in responses
        ]
        assert any(response.status_code == 201 for response in responses), [
            (response.status_code, response.text)
            for response in responses
        ]

        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as verification_session:
            bids = verification_session.scalars(
                select(Bid)
                .where(Bid.lot_id == lot_id)
                .order_by(Bid.amount.asc(), Bid.id.asc())
            ).all()

            saved_wallets = verification_session.scalars(
                select(Wallet).where(Wallet.id.in_(wallet_ids))
            ).all()
            saved_wallets_by_user = {
                wallet.user_id: wallet for wallet in saved_wallets
            }

            transactions = verification_session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.lot_id == lot_id
                )
            ).all()

            assert len(bids) in (1, 2)


            if len(bids) == 1:
    # Qualquer lance pode adquirir o bloqueio primeiro.
               assert bids[0].amount in (
               Decimal("100.00"),
               Decimal("110.00"),
          )
            else:
               assert [bid.amount for bid in bids] == [
               Decimal("100.00"),
               Decimal("110.00"),
    ]



            # No wallet can have more committed funds than its balance.
            for wallet in saved_wallets:
                assert Decimal("0.00") <= wallet.committed_balance
                assert wallet.committed_balance <= wallet.balance

            # Exactly one bidder should retain the leading reservation.
            highest_bid = bids[-1]
            leading_wallet = saved_wallets_by_user[highest_bid.bidder_id]
            assert leading_wallet.committed_balance == highest_bid.amount

            # Any non-leading bidder must have no committed reservation.
            for bidder_id in bidder_ids:
                wallet = saved_wallets_by_user[bidder_id]
                if bidder_id != highest_bid.bidder_id:
                    assert wallet.committed_balance == Decimal("0.00")

            # All financial transaction amounts must be positive.
            assert all(transaction.amount > Decimal("0.00") for transaction in transactions)

    finally:
        # Clean only records created for this lot. Preserve the global
        # append-only audit chain.
        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as cleanup_session:
            cleanup_session.query(WalletTransaction).filter(
                WalletTransaction.lot_id == lot_id
            ).delete(synchronize_session=False)
            cleanup_session.query(Bid).filter(
                Bid.lot_id == lot_id
            ).delete(synchronize_session=False)
            cleanup_session.query(Wallet).filter(
                Wallet.id.in_(wallet_ids)
            ).delete(synchronize_session=False)
            cleanup_session.query(Lot).filter(
                Lot.id == lot_id
            ).delete(synchronize_session=False)
            cleanup_session.query(User).filter(
                User.id.in_([*bidder_ids, auctioneer_id])
            ).delete(synchronize_session=False)
            cleanup_session.commit()



def test_unauthenticated_bid_does_not_change_financial_state(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro sem Token",
        email="leiloeiro.sem.token@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante sem Token",
        email="arrematante.sem.token@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote de teste sem autenticação",
        description="Teste de segurança da API",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    audit_ids_before = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()

    response = client.post(
        "/bids/",
        json={
            "lot_id": lot.id,
            "amount": "100.00",
        },
    )

    assert response.status_code == 401, response.text

    # Nenhum lance deve ter sido registrado.
    bids = db_session.scalars(
        select(Bid).where(Bid.lot_id == lot.id)
    ).all()
    assert bids == []

    # O saldo e o valor reservado devem permanecer inalterados.
    db_session.refresh(wallet)
    assert wallet.balance == Decimal("1000.00")
    assert wallet.committed_balance == Decimal("0.00")

    # Nenhuma transação financeira deve ter sido criada para o lote.
    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id
        )
    ).all()
    assert transactions == []

    # A tentativa não deve gerar eventos de auditoria.
    audit_ids_after = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()
    assert audit_ids_after == audit_ids_before


def test_insufficient_balance_does_not_change_financial_state(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro Saldo Insuficiente",
        email="leiloeiro.saldo.insuficiente@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante Saldo Insuficiente",
        email="arrematante.saldo.insuficiente@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("100.00"),
        committed_balance=Decimal("0.00"),
    )

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote para teste de saldo insuficiente",
        description="Teste de integridade financeira",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    audit_ids_before = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()

    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/bids/",
        json={
            "lot_id": lot.id,
            "amount": "110.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
    "Saldo disponível insuficiente para cobrir o lance."
)

    bids = db_session.scalars(
        select(Bid).where(Bid.lot_id == lot.id)
    ).all()
    assert bids == []

    db_session.refresh(wallet)
    assert wallet.balance == Decimal("100.00")
    assert wallet.committed_balance == Decimal("0.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id
        )
    ).all()
    assert transactions == []

    audit_ids_after = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()
    assert audit_ids_after == audit_ids_before


def test_auctioneer_cannot_bid_on_own_lot_without_financial_changes(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro do Próprio Lote",
        email="leiloeiro.proprio.lote@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )

    db_session.add(auctioneer)
    db_session.flush()

    wallet = Wallet(
        user_id=auctioneer.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote do próprio leiloeiro",
        description="Teste de bloqueio de lance próprio",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    audit_ids_before = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()

    token = create_access_token(subject=str(auctioneer.id))

    response = client.post(
        "/bids/",
        json={
            "lot_id": lot.id,
            "amount": "100.00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403, response.text

    bids = db_session.scalars(
        select(Bid).where(Bid.lot_id == lot.id)
    ).all()
    assert bids == []

    db_session.refresh(wallet)
    assert wallet.balance == Decimal("1000.00")
    assert wallet.committed_balance == Decimal("0.00")

    transactions = db_session.scalars(
        select(WalletTransaction).where(
            WalletTransaction.lot_id == lot.id
        )
    ).all()
    assert transactions == []

    audit_ids_after = db_session.scalars(
        select(AuditEvent.id).order_by(AuditEvent.id)
    ).all()
    assert audit_ids_after == audit_ids_before


def test_public_lot_bid_listing_returns_only_expected_fields_without_financial_changes(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro Listagem",
        email="leiloeiro.listagem@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante Listagem",
        email="arrematante.listagem@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("100.00"),
    )

    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote para teste de listagem",
        description="Teste da consulta pública de lances",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    first_bid = Bid(
        lot_id=lot.id,
        bidder_id=bidder.id,
        amount=Decimal("100.00"),
        created_at=now - timedelta(minutes=2),
    )
    second_bid = Bid(
        lot_id=lot.id,
        bidder_id=bidder.id,
        amount=Decimal("110.00"),
        created_at=now - timedelta(minutes=1),
    )

    db_session.add_all([first_bid, second_bid])
    db_session.flush()

    balance_before = wallet.balance
    committed_before = wallet.committed_balance

    response = client.get(f"/bids/lot/{lot.id}")

    assert response.status_code == 200, response.text

    data = response.json()
    assert len(data) == 2
    assert [item["amount"] for item in data] == ["110.00", "100.00"]

    expected_fields = {
        "id",
        "lot_id",
        "amount",
        "created_at",
    }
    assert all(set(item.keys()) == expected_fields for item in data)
    assert all("bidder_id" not in item for item in data)

    db_session.refresh(wallet)
    assert wallet.balance == balance_before
    assert wallet.committed_balance == committed_before




def test_deposit_audit_failure_rolls_back_balance_and_transaction(
    isolated_client,
    independent_engine,
):
    from app.models.audit_event import AuditEventType
    from app.models.wallet_transaction import TransactionType
    from app.api.routes import wallet as wallet_routes

    with Session(
        bind=independent_engine,
        autoflush=False,
        expire_on_commit=False,
    ) as setup_session:
        bidder = User(
            name="Arrematante Depósito Rollback",
            email="deposit.rollback@example.test",
            password_hash="hash-de-teste",
            role=UserRole.BIDDER,
        )
        setup_session.add(bidder)
        setup_session.flush()

        wallet = Wallet(
            user_id=bidder.id,
            balance=Decimal("100.00"),
            committed_balance=Decimal("0.00"),
        )
        setup_session.add(wallet)
        setup_session.flush()

        bidder_id = bidder.id
        wallet_id = wallet.id
        setup_session.commit()

    token = create_access_token(subject=str(bidder_id))

    def fail_on_wallet_transaction(db, **kwargs):
        if kwargs.get("event_type") == AuditEventType.WALLET_TRANSACTION:
            raise RuntimeError("Falha simulada na auditoria do depósito")

        from app.services.audit_service import record_event
        return record_event(db, **kwargs)

    try:
        with patch.object(
            wallet_routes,
            "record_event",
            side_effect=fail_on_wallet_transaction,
        ):
            with pytest.raises(
                RuntimeError,
                match="Falha simulada na auditoria do depósito",
            ):
                isolated_client.post(
                    "/wallet/deposit",
                    json={"amount": "50.00"},
                    headers={"Authorization": f"Bearer {token}"},
                )

        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as verification_session:
            saved_wallet = verification_session.get(Wallet, wallet_id)
            assert saved_wallet is not None
            assert saved_wallet.balance == Decimal("100.00")
            assert saved_wallet.committed_balance == Decimal("0.00")

            saved_deposits = verification_session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.wallet_id == wallet_id,
                    WalletTransaction.transaction_type
                    == TransactionType.DEPOSIT,
                )
            ).all()
            assert saved_deposits == []

    finally:
        with Session(
            bind=independent_engine,
            autoflush=False,
            expire_on_commit=False,
        ) as cleanup_session:
            cleanup_session.query(WalletTransaction).filter(
                WalletTransaction.wallet_id == wallet_id
            ).delete(synchronize_session=False)

            cleanup_session.query(Wallet).filter(
                Wallet.id == wallet_id
            ).delete(synchronize_session=False)

            cleanup_session.query(User).filter(
                User.id == bidder_id
            ).delete(synchronize_session=False)

            cleanup_session.commit()


def test_anti_sniping_persists_audit_event(
    client,
    db_session,
):
    now = datetime.now(timezone.utc)

    auctioneer = User(
        name="Leiloeiro Anti-Sniping",
        email="leiloeiro.anti.sniping@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.AUCTIONEER,
    )
    bidder = User(
        name="Arrematante Anti-Sniping",
        email="arrematante.anti.sniping@example.test",
        password_hash="hash-ficticio-apenas-para-teste",
        role=UserRole.BIDDER,
    )

    db_session.add_all([auctioneer, bidder])
    db_session.flush()

    wallet = Wallet(
        user_id=bidder.id,
        balance=Decimal("1000.00"),
        committed_balance=Decimal("0.00"),
    )
    lot = Lot(
        auctioneer_id=auctioneer.id,
        title="Lote Anti-Sniping",
        description="Teste de persistência da auditoria.",
        initial_bid=Decimal("100.00"),
        minimum_increment=Decimal("10.00"),
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(seconds=90),
        status=LotStatus.LIVE,
    )

    db_session.add_all([wallet, lot])
    db_session.flush()

    original_end = lot.ends_at
    token = create_access_token(subject=str(bidder.id))

    response = client.post(
        "/bids/",
        json={"lot_id": lot.id, "amount": "100.00"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.text

    bid_id = response.json()["id"]

    db_session.refresh(lot)

    expected_end = original_end + timedelta(minutes=2)
    assert lot.ends_at == expected_end

    event = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.event_type
            == AuditEventType.LOT_STATUS_CHANGED,
            AuditEvent.entity_type == "lot",
            AuditEvent.entity_id == lot.id,
            AuditEvent.description
            == "Encerramento prorrogado por anti-sniping.",
        )
    )

    assert event is not None, (
        "O evento de auditoria do anti-sniping não foi persistido."
    )

    assert event.actor_user_id == bidder.id
    assert event.event_data["reason"] == "bid_in_final_two_minutes"
    assert event.event_data["previous_ends_at"] == original_end.isoformat()
    assert event.event_data["new_ends_at"] == expected_end.isoformat()
    assert event.event_data["bid_id"] == bid_id

    db_session.refresh(event)
    assert event.event_hash
    assert len(event.event_hash) == 64

    chain_result = verify_audit_chain(db_session)
    assert chain_result["valid"] is True, chain_result
