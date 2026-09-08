from collections.abc import Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser
from sqlalchemy import select

from app.db.models import User, UserSettings
from app.db.session import SessionFactory


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with SessionFactory() as session:
            tg_user: TelegramUser | None = data.get("event_from_user")
            user = None
            if tg_user:
                user = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
                if not user:
                    user = User(telegram_id=tg_user.id, username=tg_user.username)
                    session.add(user)
                    await session.flush()
                    session.add(UserSettings(user_id=user.id))
            data.update(db=session, db_user=user)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
