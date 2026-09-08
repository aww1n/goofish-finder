import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from celery import shared_task
from sqlalchemy import func, or_, select

from app.collectors.base import ProviderRateLimited
from app.collectors.goofish.normalizer import Normalizer
from app.collectors.goofish.parser import detect_inspection_service
from app.collectors.goofish.provider import create_provider
from app.core.config import get_settings
from app.core.constants import NotificationMode, SearchStatus
from app.db.models import SearchFilter, SearchTask
from app.db.session import SessionFactory
from app.services.deal_score import calculate_deal_score, calculate_risk_score
from app.services.filters import passes_hard_filters
from app.services.item_service import ItemService
from app.services.market_price import calculate_market_price
from app.services.notification_service import NotificationService

log = structlog.get_logger()


async def process_search(task_id: UUID) -> int:
    provider = create_provider(get_settings())
    try:
        async with SessionFactory() as session:
            task = await session.get(SearchTask, task_id)
            if (
                not task
                or not task.enabled
                or task.deleted_at
                or task.status == SearchStatus.PAUSED
            ):
                return 0
            raws = await provider.search(task)
            normalizer = Normalizer()
            market = calculate_market_price([raw.price for raw in raws])
            search_filter = await session.get(SearchFilter, task.id)
            accepted = 0
            for raw in raws:
                normalized = normalizer.normalize(raw).as_dict()
                evidence = raw.inspection_evidence
                inspection = detect_inspection_service(
                    appraise_info=raw.appraise_info or raw.raw.get("appraiseInfo"),
                    dom_service_text=evidence.get("dom_service_text", ()),
                    accessibility_labels=evidence.get("accessibility_labels", ()),
                    element_attributes=evidence.get("element_attributes", ()),
                    page_metadata=evidence.get("page_metadata"),
                    ocr_text=evidence.get("ocr_text", ()),
                )
                normalized.update(
                    inspection_service_available=inspection.available,
                    inspection_service_mandatory=inspection.mandatory,
                    inspection_service_detected=inspection.inspection_service_detected,
                )
                if not passes_hard_filters(raw, task, normalized):
                    continue
                result = await ItemService(session).upsert(raw, normalized, inspection)
                deal = calculate_deal_score(raw, market, normalized)
                risk = calculate_risk_score(raw, market, normalized)
                result.item.deal_score, result.item.deal_breakdown = deal.score, deal.breakdown
                result.item.risk_score, result.item.risk_breakdown = risk.score, risk.breakdown
                required_score = task.min_deal_score
                if task.notification_mode == NotificationMode.DEALS:
                    required_score = max(required_score, 70)
                elif task.notification_mode == NotificationMode.SUPER:
                    required_score = max(required_score, 90)
                deal_filter_ok = True
                if search_filter and search_filter.deal_percent_below:
                    deal_filter_ok = bool(
                        market
                        and market.reliable
                        and market.median > 0
                        and (market.median - raw.price) / market.median * 100
                        >= search_filter.deal_percent_below
                    )
                ai_filter_ok = not (search_filter and search_filter.ai_only)
                if deal.score >= required_score and deal_filter_ok and ai_filter_ok:
                    kind = (
                        "price_drop" if result.old_price and raw.price < result.old_price else "new"
                    )
                    await NotificationService(session).enqueue(
                        task.user_id, task.id, result.item, kind
                    )
                    accepted += 1
            task.last_enqueued_at = datetime.now(UTC)
            task.consecutive_errors = 0
            task.status = SearchStatus.ACTIVE
            task.last_error = None
            await session.commit()
            return accepted
    finally:
        await provider.close()


@shared_task(
    bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, retry_jitter=True, max_retries=5
)
def run_search(self, task_id: str) -> int:
    try:
        return asyncio.run(process_search(UUID(task_id)))
    except ProviderRateLimited as exc:
        raise self.retry(exc=exc, countdown=min(exc.retry_after or 300, 3600), max_retries=5)


async def find_due() -> list[str]:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        tasks = await session.scalars(
            select(SearchTask)
            .where(
                SearchTask.enabled.is_(True),
                SearchTask.deleted_at.is_(None),
                SearchTask.status.in_([SearchStatus.ACTIVE, SearchStatus.ACTIVE_WITH_ERRORS]),
                or_(
                    SearchTask.last_enqueued_at.is_(None),
                    func.extract("epoch", now - SearchTask.last_enqueued_at)
                    >= SearchTask.polling_interval,
                ),
            )
            .with_for_update(skip_locked=True)
        )
        ids = []
        for task in tasks:
            task.last_enqueued_at = now
            ids.append(str(task.id))
        await session.commit()
        return ids


@shared_task
def enqueue_due_searches() -> int:
    ids = asyncio.run(find_due())
    for task_id in ids:
        run_search.apply_async(args=[task_id], task_id=f"search_task:{task_id}")
    return len(ids)
