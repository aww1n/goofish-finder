from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SearchStatus
from app.db.models import SearchTask


class SearchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, task_id: UUID, user_id: UUID) -> SearchTask | None:
        return await self.session.scalar(
            select(SearchTask).where(
                SearchTask.id == task_id,
                SearchTask.user_id == user_id,
                SearchTask.deleted_at.is_(None),
            )
        )

    async def list_owned(self, user_id: UUID) -> list[SearchTask]:
        result = await self.session.scalars(
            select(SearchTask)
            .where(SearchTask.user_id == user_id, SearchTask.deleted_at.is_(None))
            .order_by(SearchTask.created_at.desc())
        )
        return list(result)

    async def pause(self, task: SearchTask) -> None:
        task.status = SearchStatus.PAUSED
        task.enabled = False

    async def resume(self, task: SearchTask) -> None:
        task.status = SearchStatus.ACTIVE
        task.enabled = True

    async def soft_delete(self, task: SearchTask) -> None:
        task.deleted_at = datetime.now(UTC)
        task.status = SearchStatus.DISABLED
        task.enabled = False
