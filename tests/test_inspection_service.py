from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.collectors.base import RawListing
from app.collectors.goofish.parser import (
    detect_inspection_service,
    parse_appraise_info,
)
from app.core.constants import InspectionFilter
from app.services.deal_score import calculate_deal_score
from app.services.filters import passes_hard_filters


def test_structured_additional_description_marks_mandatory():
    raw = {
        "yhbVersion": "3",
        "serviceDetailTitle": "验货宝",
        "additionalDescription": "本宝贝只走验货宝",
        "serviceDescription": "下单后寄至验货中心",
        "servicePromiseItems": ["下单后逐一验货", "鉴别为真再购买"],
    }
    result = parse_appraise_info(raw)
    assert result.available is True
    assert result.mandatory is True
    assert result.type == "验货宝"
    assert result.version == "3"
    assert result.inspection_service_detected is True
    assert result.raw == raw


def test_structured_title_marks_available():
    result = parse_appraise_info({"serviceDetailTitle": "验货宝"})
    assert result.available is True
    assert result.mandatory is False


def test_product_description_mention_is_not_service_evidence():
    description = "卖家说以前听说过验货宝，但本商品不提供任何服务"
    result = detect_inspection_service()
    assert "验货宝" in description
    assert result.available is False


@pytest.mark.parametrize(
    "field,value,mandatory",
    [
        ("dom_service_text", ["支持验货宝"], False),
        ("accessibility_labels", ["必须通过验货宝"], True),
        ("element_attributes", ["title=验货宝"], False),
        ("page_metadata", {"badge": "验货宝"}, False),
        ("ocr_text", ["下单后先验货再确认购买"], False),
    ],
)
def test_fallback_detection_sources(field, value, mandatory):
    result = detect_inspection_service(**{field: value})
    assert result.available is True
    assert result.mandatory is mandatory


def _task(inspection_filter: InspectionFilter):
    return SimpleNamespace(
        min_price=None,
        max_price=None,
        storage_options=[],
        conditions=[],
        locations=[],
        seller_min_rating=None,
        seller_min_sales=None,
        inspection_filter=inspection_filter,
    )


def test_inspection_hard_filters():
    item = RawListing("1", "Bag", Decimal(100), "CNY", "https://example.test/1")
    available = {
        "inspection_service_available": True,
        "inspection_service_mandatory": False,
    }
    mandatory = {**available, "inspection_service_mandatory": True}
    absent = {
        "inspection_service_available": False,
        "inspection_service_mandatory": False,
    }
    assert passes_hard_filters(item, _task(InspectionFilter.WITH_INSPECTION), available)
    assert not passes_hard_filters(item, _task(InspectionFilter.WITH_INSPECTION), absent)
    assert passes_hard_filters(item, _task(InspectionFilter.MANDATORY_INSPECTION), mandatory)
    assert not passes_hard_filters(item, _task(InspectionFilter.MANDATORY_INSPECTION), available)
    assert passes_hard_filters(item, _task(InspectionFilter.WITHOUT_INSPECTION), absent)


def test_inspection_adds_positive_signal_without_claiming_authenticity():
    item = RawListing("1", "Bag", Decimal(100), "CNY", "https://example.test/1")
    base = calculate_deal_score(item, None, {})
    inspected = calculate_deal_score(item, None, {"inspection_service_available": True})
    assert inspected.breakdown["signals"] == base.breakdown["signals"] + 2
