from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from src.domain.entities.push_subscription import PushSubscription
from src.domain.repositories.push_subscription_repository import PushSubscriptionRepository
from src.infrastructure.database.models import PushSubscriptionModel


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


class SqlAlchemyPushSubscriptionRepository(PushSubscriptionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_user(self, user_id: int) -> list[PushSubscription]:
        stmt = (
            select(PushSubscriptionModel)
            .where(PushSubscriptionModel.user_id == user_id)
            .order_by(PushSubscriptionModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def find_for_user(self, subscription_id: int, user_id: int) -> PushSubscription | None:
        model = self._session.get(PushSubscriptionModel, subscription_id)
        if model is None or model.user_id != user_id:
            return None
        return self._to_entity(model)

    def user_ids_with_subscriptions(self) -> list[int]:
        stmt = select(PushSubscriptionModel.user_id).distinct().order_by(PushSubscriptionModel.user_id)
        return list(self._session.scalars(stmt))

    def save(self, subscription: PushSubscription) -> PushSubscription:
        digest = endpoint_hash(subscription.endpoint)
        model = self._session.scalar(
            select(PushSubscriptionModel).where(PushSubscriptionModel.endpoint_hash == digest)
        )
        if model is None:
            model = PushSubscriptionModel(
                endpoint=subscription.endpoint,
                endpoint_hash=digest,
                receives_calendar=subscription.receives_calendar,
                created_at=subscription.created_at,
            )
            self._session.add(model)
        elif model.user_id != subscription.user_id:
            # 同じ端末で別の人がログインし直した。前の人の「この端末の設定」は引き継がない
            model.receives_calendar = subscription.receives_calendar
            model.created_at = subscription.created_at
            model.last_sent_at = None
        model.user_id = subscription.user_id
        model.p256dh = subscription.p256dh
        model.auth = subscription.auth
        model.label = subscription.label
        self._session.flush()
        return self._to_entity(model)

    def set_receives_calendar(self, subscription_id: int, receives_calendar: bool) -> None:
        self._session.execute(
            update(PushSubscriptionModel)
            .where(PushSubscriptionModel.id == subscription_id)
            .values(receives_calendar=receives_calendar)
        )

    def mark_sent(self, subscription_id: int, at: datetime) -> None:
        self._session.execute(
            update(PushSubscriptionModel)
            .where(PushSubscriptionModel.id == subscription_id)
            .values(last_sent_at=at)
        )

    def delete(self, subscription_id: int) -> None:
        self._session.execute(
            delete(PushSubscriptionModel).where(PushSubscriptionModel.id == subscription_id)
        )

    @staticmethod
    def _to_entity(model: PushSubscriptionModel) -> PushSubscription:
        return PushSubscription(
            id=model.id,
            user_id=model.user_id,
            endpoint=model.endpoint,
            p256dh=model.p256dh,
            auth=model.auth,
            label=model.label,
            receives_calendar=model.receives_calendar,
            created_at=model.created_at,
            last_sent_at=model.last_sent_at,
        )
