from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.goofish.normalizer import Normalizer
from app.core.constants import InspectionFilter, NotificationMode
from app.db.models import SearchFilter, SearchTask, User
from app.db.repositories import SearchRepository


@dataclass(slots=True)
class SearchDraft:
    query: str
    max_price: Decimal
    conditions: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    seller_min_rating: Decimal | None = None
    seller_min_sales: int | None = None
    inspection_filter: InspectionFilter = InspectionFilter.ANY
    min_deal_score: int = 0
    deal_percent_below: int | None = None
    ai_only: bool = False
    notification_mode: NotificationMode = NotificationMode.DEALS
    notification_limit_hour: int | None = 10
    polling_interval: int = 900


def parse_price(value: str) -> Decimal:
    clean = value.strip().replace("¥", "").replace(" ", "").replace(",", ".")
    try:
        price = Decimal(clean).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("Введите корректное положительное число") from exc
    if price <= 0 or price > Decimal(100000000):
        raise ValueError("Цена вне допустимого диапазона")
    return price


class SearchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SearchRepository(session)

    async def create(self, user: User, draft: SearchDraft) -> SearchTask:
        if not draft.query.strip() or len(draft.query) > 255:
            raise ValueError("Название должно содержать от 1 до 255 символов")
        parsed = Normalizer().normalize_query(draft.query)
        task = SearchTask(
            user_id=user.id,
            query=draft.query.strip(),
            normalized_brand=parsed.brand,
            normalized_model=parsed.model,
            storage_options=[str(parsed.storage_gb)] if parsed.storage_gb else [],
            max_price=draft.max_price,
            conditions=draft.conditions,
            locations=draft.locations,
            seller_min_rating=draft.seller_min_rating,
            seller_min_sales=draft.seller_min_sales,
            inspection_filter=draft.inspection_filter,
            min_deal_score=draft.min_deal_score,
            notification_mode=draft.notification_mode,
            notification_limit_hour=draft.notification_limit_hour,
            polling_interval=draft.polling_interval,
        )
        task.filters = SearchFilter(
            deal_percent_below=draft.deal_percent_below, ai_only=draft.ai_only
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def set_paused(self, task_id: UUID, user_id: UUID, paused: bool) -> SearchTask:
        task = await self.repo.get_owned(task_id, user_id)
        if not task:
            raise PermissionError("Поиск не найден")
        await (self.repo.pause(task) if paused else self.repo.resume(task))
        return task

    async def delete(self, task_id: UUID, user_id: UUID) -> None:
        task = await self.repo.get_owned(task_id, user_id)
        if not task:
            raise PermissionError("Поиск не найден")
        await self.repo.soft_delete(task)
