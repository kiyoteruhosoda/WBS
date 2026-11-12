from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.login_transaction import LoginPurpose, LoginTransaction
from src.domain.repositories.login_transaction_repository import LoginTransactionRepository
from src.domain.value_objects.continued_sign_in import ContinuedSignIn
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
            silent=transaction.silent,
            purpose=transaction.purpose.value,
            continued_user_id=transaction.continued.user_id if transaction.continued else None,
            continued_session_id=transaction.continued.session_id if transaction.continued else None,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        transaction.id = model.id
        return transaction

    def find(self, state: str) -> LoginTransaction | None:
        stmt = select(LoginTransactionModel).where(LoginTransactionModel.state == state)
        model = self._session.scalars(stmt).first()
        return None if model is None else self._to_entity(model)

    def consume(self, state: str) -> LoginTransaction | None:
        stmt = select(LoginTransactionModel).where(LoginTransactionModel.state == state)
        model = self._session.scalars(stmt).first()
        if model is None:
            return None
        entity = self._to_entity(model)
        # Delete it right when it is taken out, so a resend with the same state (= same authorization code) does not pass.
        # The delete is a conditional DELETE, and the row is returned only if we were the one that removed it. Otherwise,
        # if another request took the same row between our read and our delete, the round trip that should be one-shot
        # would succeed there too (possible with a double-submitted callback).
        deleted = self._session.execute(
            delete(LoginTransactionModel).where(LoginTransactionModel.id == model.id)
        )
        self._session.commit()
        if not deleted.rowcount:
            return None
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
            silent=model.silent,
            # Unknown values (e.g. rows after a downgrade) are read as a normal login
            purpose=LoginPurpose.RENEW if model.purpose == LoginPurpose.RENEW.value else LoginPurpose.LOGIN,
            continued=_continued_of(model),
        )


def _continued_of(model: LoginTransactionModel) -> ContinuedSignIn | None:
    if model.continued_user_id is None or model.continued_session_id is None:
        return None
    return ContinuedSignIn(user_id=model.continued_user_id, session_id=model.continued_session_id)
