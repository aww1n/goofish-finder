from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.constants import InspectionFilter, NotificationMode, SearchStatus

JSON_DICT = JSON().with_variant(JSONB(), "postgresql")
JSON_LIST = JSON().with_variant(JSONB(), "postgresql")


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {dict[str, Any]: JSON_DICT, list[str]: JSON_LIST}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    searches: Mapped[list["SearchTask"]] = relationship(back_populates="user")
    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False)


class UserSettings(Base, TimestampMixin):
    __tablename__ = "user_settings"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    language: Mapped[str] = mapped_column(String(8), default="ru")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    quiet_from: Mapped[time] = mapped_column(Time, default=time(23, 0))
    quiet_to: Mapped[time] = mapped_column(Time, default=time(8, 0))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    digest_mode: Mapped[str] = mapped_column(String(16), default="off")
    digest_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    min_deal_score: Mapped[int] = mapped_column(Integer, default=70)
    user: Mapped[User] = relationship(back_populates="settings")


class SearchTask(Base, TimestampMixin):
    __tablename__ = "search_tasks"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(255))
    normalized_brand: Mapped[str | None] = mapped_column(String(80))
    normalized_model: Mapped[str | None] = mapped_column(String(160))
    storage_options: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON_LIST), default=list
    )
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    conditions: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON_LIST), default=list)
    locations: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON_LIST), default=list)
    seller_min_rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    seller_min_sales: Mapped[int | None] = mapped_column(Integer)
    min_deal_score: Mapped[int] = mapped_column(Integer, default=0)
    inspection_filter: Mapped[InspectionFilter] = mapped_column(
        SAEnum(InspectionFilter), default=InspectionFilter.ANY
    )
    notification_mode: Mapped[NotificationMode] = mapped_column(
        SAEnum(NotificationMode), default=NotificationMode.DEALS
    )
    notification_limit_hour: Mapped[int | None] = mapped_column(Integer, default=10)
    polling_interval: Mapped[int] = mapped_column(Integer, default=900)
    status: Mapped[SearchStatus] = mapped_column(
        SAEnum(SearchStatus), default=SearchStatus.ACTIVE, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship(back_populates="searches")
    filters: Mapped["SearchFilter"] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )


class SearchFilter(Base):
    __tablename__ = "search_filters"
    search_task_id: Mapped[UUID] = mapped_column(
        ForeignKey("search_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    deal_percent_below: Mapped[int | None] = mapped_column(Integer)
    ai_only: Mapped[bool] = mapped_column(Boolean, default=False)
    track_price_changes: Mapped[bool] = mapped_column(Boolean, default=False)
    extra: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSON_DICT), default=dict)
    task: Mapped[SearchTask] = relationship(back_populates="filters")


class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_id: Mapped[str] = mapped_column(String(160), unique=True)
    name: Mapped[str | None] = mapped_column(String(160))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    sales_count: Mapped[int | None] = mapped_column(Integer)


class Item(Base, TimestampMixin):
    __tablename__ = "items"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    external_item_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    seller_id: Mapped[UUID | None] = mapped_column(ForeignKey("sellers.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    url: Mapped[str] = mapped_column(String(1000))
    location: Mapped[str | None] = mapped_column(String(160))
    condition: Mapped[str | None] = mapped_column(String(32))
    normalized: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON_DICT), default=dict
    )
    raw_data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON_DICT), default=dict
    )
    inspection_service_available: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_service_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    inspection_service_type: Mapped[str | None] = mapped_column(String(64))
    inspection_service_version: Mapped[str | None] = mapped_column(String(32))
    inspection_service_description: Mapped[str | None] = mapped_column(Text)
    inspection_service_url: Mapped[str | None] = mapped_column(Text)
    inspection_service_raw: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON_DICT), default=dict
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    deal_score: Mapped[int | None] = mapped_column(Integer)
    deal_breakdown: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON_DICT), default=dict
    )
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_breakdown: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON_DICT), default=dict
    )
    seller: Mapped[Seller | None] = relationship()
    images: Mapped[list["ItemImage"]] = relationship(cascade="all, delete-orphan")


class ItemImage(Base):
    __tablename__ = "item_images"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    position: Mapped[int] = mapped_column(Integer, default=0)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("item_id", "price", "recorded_at", name="uq_price_version"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    signature: Mapped[str] = mapped_column(String(255), index=True)
    median: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    average: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    minimum: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    maximum: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    percentile_25: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    sample_size: Mapped[int] = mapped_column(Integer)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_alert_idempotency"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    search_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("search_tasks.id", ondelete="SET NULL"), index=True
    )
    item_id: Mapped[UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    notification_type: Mapped[str] = mapped_column(String(32))
    price_version: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Favorite(Base):
    __tablename__ = "favorites"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HiddenItem(Base):
    __tablename__ = "hidden_items"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TrackedItem(Base):
    __tablename__ = "tracked_items"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    track_price: Mapped[bool] = mapped_column(Boolean, default=True)
    track_status: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


Index("ix_task_due", SearchTask.status, SearchTask.last_enqueued_at)

__all__ = [
    "Alert",
    "Base",
    "Favorite",
    "HiddenItem",
    "Item",
    "ItemImage",
    "MarketPrice",
    "PriceHistory",
    "SearchFilter",
    "SearchTask",
    "Seller",
    "TrackedItem",
    "User",
    "UserSettings",
]
