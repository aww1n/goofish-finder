from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.collectors.base import GoofishProvider, RawListing, RawSeller
from app.collectors.goofish.browser_provider import BrowserGoofishProvider
from app.core.config import Settings


class MockGoofishProvider(GoofishProvider):
    """Deterministic provider for local development and end-to-end UX testing."""

    def __init__(self) -> None:
        self._items = [
            RawListing(
                external_id="mock-iphone-001",
                title="Apple 苹果 iPhone 16 Pro 128G 国行 99新",
                price=Decimal(4090),
                currency="CNY",
                url="https://www.goofish.com/item/mock-iphone-001",
                images=["https://picsum.photos/seed/goofish1/800/800"],
                description="自用，功能正常，配件齐全",
                seller=RawSeller("mock-seller-1", "上海数码", Decimal(98), 326),
                location="Shanghai",
                condition="99新",
                published_at=datetime.now(UTC),
                appraise_info={
                    "yhbVersion": "3",
                    "serviceDetailTitle": "验货宝",
                    "additionalDescription": "本宝贝只走验货宝",
                    "serviceDescription": "下单后寄至验货中心，非正品无条件急速退款",
                    "servicePromiseItems": ["下单后逐一验货", "鉴别为真再购买"],
                },
            ),
            RawListing(
                external_id="mock-iphone-002",
                title="iPhone 16 Pro 128GB 95新",
                price=Decimal(4450),
                currency="CNY",
                url="https://www.goofish.com/item/mock-iphone-002",
                description="正常使用痕迹",
                seller=RawSeller("mock-seller-2", "个人卖家", Decimal(95), 42),
                location="Beijing",
                condition="95新",
                published_at=datetime.now(UTC),
            ),
        ]

    async def search(self, task: Any, *, page: int = 1) -> list[RawListing]:
        return list(self._items) if page == 1 else []

    async def get_item_details(self, item_id: str) -> RawListing:
        return next(item for item in self._items if item.external_id == item_id)


def create_provider(settings: Settings) -> GoofishProvider:
    if settings.goofish_provider == "mock":
        return MockGoofishProvider()
    if settings.goofish_provider == "browser":
        return BrowserGoofishProvider(settings)
    raise RuntimeError(
        "Real Goofish provider is not configured. Use GOOFISH_PROVIDER=mock or implement an authorized provider."
    )
