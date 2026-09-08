from datetime import UTC, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.bot.handlers.search import draft_is_complete
from app.bot.keyboards.common import multi_keyboard
from app.collectors.base import RawListing, RawSeller
from app.collectors.goofish.normalizer import Normalizer
from app.services.deal_score import calculate_deal_score, calculate_risk_score
from app.services.filters import passes_hard_filters
from app.services.market_price import calculate_market_price
from app.services.notification_service import alert_key, is_quiet_time
from app.services.search_service import parse_price


def listing(price: str = "4000") -> RawListing:
    return RawListing(
        "x",
        "Apple iPhone 16 Pro 128G 99新",
        Decimal(price),
        "CNY",
        "https://example.test/x",
        ["https://example.test/a.jpg"],
        "完整描述，功能正常",
        RawSeller("s", rating=Decimal(98), sales_count=100),
        "Shanghai",
        "99新",
    )


def test_query_normalization():
    value = Normalizer().normalize_query("Apple 苹果 iPhone 16 Pro 128G 国行")
    assert (value.brand, value.model, value.storage_gb) == ("Apple", "iPhone 16 Pro", 128)


def test_market_price_requires_sample_for_reliability():
    market = calculate_market_price([Decimal(x) for x in ("4000", "4500", "5000", "5500", "6000")])
    assert market and market.median == Decimal(5000) and market.reliable


def test_deal_and_risk_scores_have_breakdown():
    item = listing()
    normalized = Normalizer().normalize(item).as_dict()
    market = calculate_market_price([Decimal(x) for x in ("4800", "4900", "5000", "5100", "5200")])
    deal = calculate_deal_score(item, market, normalized)
    risk = calculate_risk_score(item, market, normalized)
    assert deal.score >= 80 and sum(deal.breakdown.values()) == deal.score
    assert 0 <= risk.score <= 100


def test_hard_filters_stop_mismatch():
    task = SimpleNamespace(
        min_price=None,
        max_price=Decimal(4500),
        storage_options=["128"],
        conditions=["99new"],
        locations=["Shanghai"],
        seller_min_rating=Decimal(95),
        seller_min_sales=50,
    )
    item = listing()
    assert passes_hard_filters(item, task, Normalizer().normalize(item).as_dict())
    task.max_price = Decimal(3000)
    assert not passes_hard_filters(item, task, Normalizer().normalize(item).as_dict())


@pytest.mark.parametrize(
    "raw,expected", [("¥4 500", Decimal("4500.00")), ("4090.5", Decimal("4090.50"))]
)
def test_decimal_price(raw, expected):
    assert parse_price(raw) == expected


def test_alert_idempotency_key_price_version():
    user, item = uuid4(), uuid4()
    assert alert_key(user, item, "new", Decimal(100)) == alert_key(user, item, "new", Decimal(100))
    assert alert_key(user, item, "new", Decimal(100)) != alert_key(user, item, "new", Decimal(90))


def test_overnight_quiet_hours():
    settings = SimpleNamespace(
        quiet_hours_enabled=True, timezone="UTC", quiet_from=time(23), quiet_to=time(8)
    )
    assert is_quiet_time(settings, datetime(2026, 1, 1, 1, tzinfo=UTC))
    assert not is_quiet_time(settings, datetime(2026, 1, 1, 12, tzinfo=UTC))


def test_multi_select_keyboard_has_one_button_per_option():
    keyboard = multi_keyboard("s:c", [("new", "Новое"), ("used", "Б/у")], {"new"}, "s:c:done")
    assert [len(row) for row in keyboard.inline_keyboard] == [1, 1, 1, 1]
    assert keyboard.inline_keyboard[0][0].text == "☑ Новое"
    assert keyboard.inline_keyboard[1][0].callback_data == "s:c:used"


def test_search_wizard_rejects_incomplete_state():
    assert draft_is_complete({"query": "iPhone", "max_price": "4500"})
    assert not draft_is_complete({"max_price": "4500"})
    assert not draft_is_complete({"query": "iPhone"})
