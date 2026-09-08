import asyncio
from datetime import UTC, datetime
from uuid import UUID

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from celery import shared_task
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Alert, Item, SearchTask, User, UserSettings
from app.db.session import SessionFactory
from app.services.notification_service import NotificationService, is_quiet_time


async def send_alert(alert_id: UUID) -> bool:
    async with SessionFactory() as session:
        alert = await session.get(Alert, alert_id)
        if not alert or alert.status != "pending":
            return False
        user = await session.get(User, alert.user_id)
        item = await session.get(Item, alert.item_id)
        settings = await session.get(UserSettings, alert.user_id)
        if not user or not item or not settings or is_quiet_time(settings):
            return False
        task = await session.get(SearchTask, alert.search_task_id) if alert.search_task_id else None
        if not await NotificationService(session).within_hourly_limit(
            user.id, task.notification_limit_hour if task else 10
        ):
            return False
        caption = (
            f"🔥 НОВАЯ НАХОДКА\n\n📱 {item.title}\n💰 ¥{item.price:,.0f}\n"
            f"🔥 Deal Score: {item.deal_score}/100\n📍 {item.location or 'Не указан'}\n"
            f"🛡 Risk Score: {item.risk_score}/100"
        )
        if item.inspection_service_available:
            inspection_status = "ОБЯЗАТЕЛЬНО" if item.inspection_service_mandatory else "Есть"
            caption += f"\n🛡 验货宝 (проверка товара): {inspection_status}"
        token = get_settings().bot_token.get_secret_value()
        if not token:
            return False
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Открыть Goofish", url=item.url)],
                [
                    InlineKeyboardButton(text="📊 Подробнее", callback_data=f"i:v:{item.id}"),
                    InlineKeyboardButton(text="⭐ Сохранить", callback_data=f"i:s:{item.id}"),
                ],
                [
                    InlineKeyboardButton(
                        text="🤔 Почему это выгодно?", callback_data=f"i:why:{item.id}"
                    )
                ],
                [InlineKeyboardButton(text="🚫 Скрыть", callback_data=f"i:h:{item.id}")],
            ]
        )
        async with Bot(token) as bot:
            await bot.send_message(user.telegram_id, caption, reply_markup=keyboard)
        alert.status = "sent"
        alert.sent_at = datetime.now(UTC)
        await session.commit()
        return True


@shared_task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, max_retries=5)
def deliver_alert(self, alert_id: str) -> bool:
    return asyncio.run(send_alert(UUID(alert_id)))


async def pending_ids() -> list[str]:
    async with SessionFactory() as session:
        values = await session.scalars(select(Alert.id).where(Alert.status == "pending").limit(100))
        return [str(value) for value in values]


@shared_task
def dispatch_pending_alerts() -> int:
    ids = asyncio.run(pending_ids())
    for alert_id in ids:
        deliver_alert.apply_async(args=[alert_id], task_id=f"notification:{alert_id}")
    return len(ids)
