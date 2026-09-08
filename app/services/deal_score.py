from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.collectors.base import RawListing
from app.services.market_price import MarketData


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: int
    breakdown: dict[str, int]


def calculate_deal_score(
    item: RawListing, market: MarketData | None, normalized: dict[str, Any]
) -> ScoreResult:
    price_points = 20
    if market and market.reliable and market.median > 0:
        discount = (market.median - item.price) / market.median
        price_points = max(0, min(40, round(20 + discount * 100)))
    condition_points = {"new": 20, "99new": 18, "95new": 15, "90new": 12, "defects": 3}.get(
        normalized.get("condition"), 8
    )
    seller_points = 5
    if item.seller and item.seller.rating is not None:
        seller_points = min(15, round(Decimal(item.seller.rating) / Decimal(100) * 15))
    description_points = min(10, 3 + len(item.description or "") // 20)
    completeness = min(5, sum(value is not None for value in normalized.values()))
    signals = 3 + min(3, len(item.images) * 2)
    if item.url.startswith("https://"):
        signals += 2
    if normalized.get("inspection_service_available") is True:
        signals += 2
    breakdown = {
        "price": price_points,
        "condition": condition_points,
        "seller": seller_points,
        "description": description_points,
        "completeness": completeness,
        "signals": signals,
    }
    return ScoreResult(min(100, sum(breakdown.values())), breakdown)


def inspection_explanation(normalized: dict[str, Any]) -> str | None:
    if normalized.get("inspection_service_mandatory") is True:
        status = "обязательная проверка"
    elif normalized.get("inspection_service_available") is True:
        status = "доступен"
    else:
        return None
    return (
        f"🛡 验货宝 (проверка товара): {status}\n"
        "Объявление поддерживает сервис 验货宝. Это снижает риск покупки "
        "неподтверждённого товара, однако наличие сервиса само по себе не означает, "
        "что товар уже прошёл проверку."
    )


def calculate_risk_score(
    item: RawListing, market: MarketData | None, normalized: dict[str, Any]
) -> ScoreResult:
    breakdown: dict[str, int] = {}
    if market and market.reliable and market.median and item.price < market.median * Decimal("0.5"):
        breakdown["unusually_low_price"] = 35
    if not item.seller or item.seller.rating is None:
        breakdown["seller_data_missing"] = 15
    elif item.seller.rating < 90:
        breakdown["low_seller_rating"] = 20
    if not item.description:
        breakdown["description_missing"] = 15
    if not item.images:
        breakdown["images_missing"] = 10
    if any(
        word in (item.title + " " + (item.description or "")).lower()
        for word in ("先款", "定金", "微信")
    ):
        breakdown["suspicious_text"] = 25
    if not normalized.get("model"):
        breakdown["model_unclear"] = 5
    return ScoreResult(min(100, sum(breakdown.values())), breakdown)
