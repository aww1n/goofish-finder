from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import RawListing
from app.collectors.goofish.parser import InspectionService
from app.db.models import Item, ItemImage, PriceHistory, Seller


@dataclass(frozen=True, slots=True)
class UpsertResult:
    item: Item
    created: bool
    old_price: Decimal | None = None


class ItemService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        raw: RawListing,
        normalized: dict[str, object],
        inspection: InspectionService | None = None,
    ) -> UpsertResult:
        item = await self.session.scalar(
            select(Item).where(Item.external_item_id == raw.external_id)
        )
        timestamp = datetime.now(UTC)
        inspection = inspection or InspectionService()
        if item:
            old_price = item.price
            item.last_seen_at = timestamp
            item.status = "active"
            self._set_inspection(item, inspection)
            if old_price != raw.price:
                item.price = raw.price
                self.session.add(
                    PriceHistory(item_id=item.id, price=raw.price, recorded_at=timestamp)
                )
            return UpsertResult(item, False, old_price if old_price != raw.price else None)

        seller = None
        if raw.seller:
            seller = await self.session.scalar(
                select(Seller).where(Seller.external_id == raw.seller.external_id)
            )
            if not seller:
                seller = Seller(
                    external_id=raw.seller.external_id,
                    name=raw.seller.name,
                    rating=raw.seller.rating,
                    sales_count=raw.seller.sales_count,
                )
                self.session.add(seller)
                await self.session.flush()
        item = Item(
            external_item_id=raw.external_id,
            seller_id=seller.id if seller else None,
            title=raw.title,
            description=raw.description,
            price=raw.price,
            currency=raw.currency,
            url=raw.url,
            location=raw.location,
            condition=raw.condition,
            normalized=normalized,
            raw_data=raw.raw,
            inspection_service_available=inspection.available,
            inspection_service_mandatory=inspection.mandatory,
            inspection_service_type=inspection.type,
            inspection_service_version=inspection.version,
            inspection_service_description=inspection.description,
            inspection_service_url=inspection.service_url,
            inspection_service_raw=inspection.raw,
            published_at=raw.published_at,
            first_seen_at=timestamp,
            last_seen_at=timestamp,
        )
        self.session.add(item)
        await self.session.flush()
        self.session.add(PriceHistory(item_id=item.id, price=raw.price, recorded_at=timestamp))
        for position, url in enumerate(raw.images):
            self.session.add(ItemImage(item_id=item.id, url=url, position=position))
        return UpsertResult(item, True)

    @staticmethod
    def _set_inspection(item: Item, inspection: InspectionService) -> None:
        item.inspection_service_available = inspection.available
        item.inspection_service_mandatory = inspection.mandatory
        item.inspection_service_type = inspection.type
        item.inspection_service_version = inspection.version
        item.inspection_service_description = inspection.description
        item.inspection_service_url = inspection.service_url
        item.inspection_service_raw = inspection.raw
