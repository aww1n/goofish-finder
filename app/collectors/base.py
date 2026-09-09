from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class RawSeller:
    external_id: str
    name: str | None = None
    rating: Decimal | None = None
    sales_count: int | None = None


@dataclass(slots=True)
class RawListing:
    external_id: str
    title: str
    price: Decimal
    currency: str
    url: str
    images: list[str] = field(default_factory=list)
    description: str | None = None
    seller: RawSeller | None = None
    location: str | None = None
    condition: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    appraise_info: dict[str, Any] | None = None
    inspection_evidence: dict[str, Any] = field(default_factory=dict)


RawListingDetails = RawListing


class ProviderError(RuntimeError):
    """Temporary provider failure."""


class ProviderRateLimited(ProviderError):
    def __init__(self, retry_after: int | None = None):
        super().__init__("provider rate limit reached")
        self.retry_after = retry_after


class ProviderAuthRequired(ProviderError):
    """The provider requires an interactive, user-authorized login."""


class ProviderAccessChallenge(ProviderError):
    """The source presented CAPTCHA or another access challenge."""


class GoofishProvider(ABC):
    @abstractmethod
    async def search(self, task: Any, *, page: int = 1) -> list[RawListing]: ...

    @abstractmethod
    async def get_item_details(self, item_id: str) -> RawListingDetails: ...

    async def close(self) -> None:
        pass
