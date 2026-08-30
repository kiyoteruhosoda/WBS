from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.login_transaction import LoginTransaction
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.value_objects.redirect_target import RedirectTarget
from src.infrastructure.database.models import LoginTransactionModel


class SqlAlchemyLoginTransactionRepository(LoginTransactionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, transaction: LoginTransaction) -> LoginTransaction:
        model = LoginTransactionModel(
            state=transaction.state,
            nonce=transaction.nonce,
            code_verifier=transaction.code_verifier,
            redirect_path=transaction.redirect_target.path,
            created_at=transaction.created_at,
            expires_at=transaction.expires_at,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        transaction.id = model.id
        return transaction

    def consume(self, state: str) -> LoginTransaction | None:
        stmt = select(LoginTransactionModel).where(LoginTransactionModel.state == state)
        model = self._session.scalars(stmt).first()
        if model is None:
            return None
        entity = self._to_entity(model)
        # 取り出したその場で消す。同じ state（＝同じ認可コード）での再送を通さない。
        self._session.delete(model)
        self._session.commit()
        return entity

    def delete_expired(self, now: datetime) -> int:
        result = self._session.execute(
            delete(LoginTransactionModel).where(LoginTransactionModel.expires_at < now)
        )
        self._session.commit()
        return result.rowcount or 0

    @staticmethod
    def _to_entity(model: LoginTransactionModel) -> LoginTransaction:
        return LoginTransaction(
            id=model.id,
            state=model.state,
            nonce=model.nonce,
            code_verifier=model.code_verifier,
            redirect_target=RedirectTarget.parse(model.redirect_path),
            created_at=model.created_at,
            expires_at=model.expires_at,
        )
