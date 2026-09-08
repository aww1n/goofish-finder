from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Favorite, HiddenItem, Item


class FavoriteService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_id: UUID, item_id: UUID) -> None:
        if not await self.session.get(Item, item_id):
            raise LookupError("Объявление не найдено")
        if not await self.session.get(Favorite, (user_id, item_id)):
            self.session.add(Favorite(user_id=user_id, item_id=item_id))

    async def remove(self, user_id: UUID, item_id: UUID) -> None:
        await self.session.execute(
            delete(Favorite).where(Favorite.user_id == user_id, Favorite.item_id == item_id)
        )

    async def hide(self, user_id: UUID, item_id: UUID, reason: str | None = None) -> None:
        if not await self.session.get(HiddenItem, (user_id, item_id)):
            self.session.add(
                HiddenItem(user_id=user_id, item_id=item_id, reason=(reason or "")[:255])
            )

    async def is_hidden(self, user_id: UUID, item_id: UUID) -> bool:
        return bool(
            await self.session.scalar(
                select(HiddenItem).where(
                    HiddenItem.user_id == user_id, HiddenItem.item_id == item_id
                )
            )
        )
