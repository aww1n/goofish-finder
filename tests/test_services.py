from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.collectors.base import RawListing
from app.collectors.goofish.parser import parse_appraise_info
from app.core.constants import SearchStatus
from app.db.models import Favorite, HiddenItem, PriceHistory, User, UserSettings
from app.db.repositories import SearchRepository
from app.services.favorite_service import FavoriteService
from app.services.item_service import ItemService
from app.services.notification_service import NotificationService
from app.services.search_service import SearchDraft, SearchService


async def make_user(db, telegram_id: int = 1) -> User:
    user = User(telegram_id=telegram_id)
    db.add(user)
    await db.flush()
    db.add(UserSettings(user_id=user.id))
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_create_modify_pause_and_soft_delete_search(db):
    user = await make_user(db)
    service = SearchService(db)
    task = await service.create(user, SearchDraft("iPhone 16 Pro 128GB", Decimal(4500)))
    assert task.normalized_model == "iPhone 16 Pro" and task.storage_options == ["128"]
    task.max_price = Decimal(4200)
    await service.set_paused(task.id, user.id, True)
    assert task.status == SearchStatus.PAUSED and task.max_price == Decimal(4200)
    await service.delete(task.id, user.id)
    assert task.deleted_at is not None and not task.enabled


@pytest.mark.asyncio
async def test_callback_style_authorization_blocks_other_user(db):
    owner = await make_user(db, 10)
    stranger = await make_user(db, 11)
    task = await SearchService(db).create(owner, SearchDraft("Phone", Decimal(1000)))
    assert await SearchRepository(db).get_owned(task.id, stranger.id) is None
    with pytest.raises(PermissionError):
        await SearchService(db).set_paused(task.id, stranger.id, True)


@pytest.mark.asyncio
async def test_item_deduplication_and_price_change(db):
    service = ItemService(db)
    raw = RawListing("same-id", "Phone", Decimal(100), "CNY", "https://example.test/item")
    first = await service.upsert(raw, {})
    second = await service.upsert(raw, {})
    assert first.created and not second.created and first.item.id == second.item.id
    raw.price = Decimal(90)
    changed = await service.upsert(raw, {})
    await db.flush()
    count = await db.scalar(
        select(func.count()).select_from(PriceHistory).where(PriceHistory.item_id == first.item.id)
    )
    assert changed.old_price == Decimal(100) and count == 2


@pytest.mark.asyncio
async def test_favorite_and_hidden_relations_are_user_scoped(db):
    user = await make_user(db)
    item = (
        await ItemService(db).upsert(
            RawListing("favorite-id", "Phone", Decimal(100), "CNY", "https://example.test/item"), {}
        )
    ).item
    service = FavoriteService(db)
    await service.add(user.id, item.id)
    await service.hide(user.id, item.id)
    await db.flush()
    assert await db.get(Favorite, (user.id, item.id))
    assert await db.get(HiddenItem, (user.id, item.id)) and await service.is_hidden(
        user.id, item.id
    )
    await service.remove(user.id, item.id)
    await db.flush()
    assert await db.get(Favorite, (user.id, item.id)) is None


@pytest.mark.asyncio
async def test_alert_deduplication(db):
    user = await make_user(db)
    task = await SearchService(db).create(user, SearchDraft("Phone", Decimal(1000)))
    item = (
        await ItemService(db).upsert(
            RawListing("alert-id", "Phone", Decimal(100), "CNY", "https://example.test/item"), {}
        )
    ).item
    service = NotificationService(db)
    first = await service.enqueue(user.id, task.id, item)
    duplicate = await service.enqueue(user.id, task.id, item)
    assert first is not None and duplicate is None


@pytest.mark.asyncio
async def test_notification_hourly_limit(db):
    user = await make_user(db)
    task = await SearchService(db).create(user, SearchDraft("Phone", Decimal(1000)))
    item = (
        await ItemService(db).upsert(
            RawListing("limit-id", "Phone", Decimal(100), "CNY", "https://example.test/item"), {}
        )
    ).item
    service = NotificationService(db)
    alert = await service.enqueue(user.id, task.id, item)
    alert.sent_at = datetime.now(UTC)
    alert.status = "sent"
    await db.flush()
    assert not await service.within_hourly_limit(user.id, 1)
    assert await service.within_hourly_limit(user.id, 2)


@pytest.mark.asyncio
async def test_item_persists_raw_inspection_data(db):
    raw_data = {
        "serviceDetailTitle": "验货宝",
        "additionalDescription": "本宝贝只走验货宝",
    }
    item = (
        await ItemService(db).upsert(
            RawListing("inspection-id", "Bag", Decimal(100), "CNY", "https://example.test/i"),
            {},
            parse_appraise_info(raw_data),
        )
    ).item
    await db.flush()
    assert item.inspection_service_available is True
    assert item.inspection_service_mandatory is True
    assert item.inspection_service_raw == raw_data
