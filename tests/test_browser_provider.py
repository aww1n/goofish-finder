from decimal import Decimal

import pytest

from app.collectors.base import ProviderAccessChallenge
from app.collectors.goofish.browser_provider import (
    BrowserGoofishProvider,
    external_id_from_url,
    price_from_text,
    title_from_text,
)


def test_external_item_id_comes_from_observed_item_url():
    assert (
        external_id_from_url("https://www.goofish.com/item?categoryId=0&id=1045257377460")
        == "1045257377460"
    )
    assert external_id_from_url("https://www.goofish.com/search?q=iPhone") is None


def test_search_card_price_and_title_parsing():
    text = "iPhone 16 Pro 128G\n几乎全新\n¥\n4,090\n5人想要\n卖家信用极好"
    assert price_from_text(text) == Decimal(4090)
    assert title_from_text(text) == "iPhone 16 Pro 128G"


def test_appraise_info_is_found_recursively_in_captured_json():
    expected = {"serviceDetailTitle": "验货宝", "yhbVersion": "3"}
    payload = {"data": {"item": {"appraiseInfo": expected}}}
    assert BrowserGoofishProvider._find_mapping([payload], "appraiseInfo") == expected


def test_challenge_detection_does_not_bypass_access_control():
    with pytest.raises(ProviderAccessChallenge):
        BrowserGoofishProvider._validate_access("请完成验证")
