from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, Item, UserSettings


def is_quiet_time(settings: UserSettings, at: datetime | None = None) -> bool:
    if not settings.quiet_hours_enabled:
        return False
    local = (
        (at or datetime.now(UTC))
        .astimezone(ZoneInfo(settings.timezone))
        .time()
        .replace(tzinfo=None)
    )
    start, end = settings.quiet_from, settings.quiet_to
    return start <= local < end if start < end else local >= start or local < end


def alert_key(user_id: UUID, item_id: UUID, kind: str, price: Decimal) -> str:
    return f"{user_id}:{item_id}:{kind}:{price}"


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(
        self, user_id: UUID, task_id: UUID, item: Item, kind: str = "new"
    ) -> Alert | None:
        key = alert_key(user_id, item.id, kind, item.price)
        if await self.session.scalar(select(Alert.id).where(Alert.idempotency_key == key)):
            return None
        alert = Alert(
            user_id=user_id,
            search_task_id=task_id,
            item_id=item.id,
            notification_type=kind,
            price_version=str(item.price),
            idempotency_key=key,
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def within_hourly_limit(self, user_id: UUID, limit: int | None) -> bool:
        if limit is None:
            return True
        count = await self.session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.user_id == user_id, Alert.sent_at >= datetime.now(UTC) - timedelta(hours=1)
            )
        )
        return (count or 0) < limit
