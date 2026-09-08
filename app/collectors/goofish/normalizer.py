import re
from dataclasses import dataclass

from app.collectors.base import RawListing

BRANDS = {"apple": "Apple", "苹果": "Apple", "samsung": "Samsung", "三星": "Samsung"}
REGIONS = {
    "上海": "Shanghai",
    "北京": "Beijing",
    "广州": "Guangzhou",
    "深圳": "Shenzhen",
    "杭州": "Hangzhou",
}
CONDITIONS = {"全新": "new", "99新": "99new", "95新": "95new", "9成新": "90new"}


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    brand: str | None
    model: str | None
    storage_gb: int | None
    region: str | None
    condition: str | None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "brand": self.brand,
            "model": self.model,
            "storage_gb": self.storage_gb,
            "region": self.region,
            "condition": self.condition,
        }


class Normalizer:
    def normalize_query(self, text: str) -> NormalizedListing:
        return self._normalize(text, None, None)

    def normalize(self, item: RawListing) -> NormalizedListing:
        return self._normalize(
            f"{item.title} {item.description or ''}", item.location, item.condition
        )

    def _normalize(
        self, text: str, location: str | None, condition: str | None
    ) -> NormalizedListing:
        lower = text.lower()
        brand = next((value for key, value in BRANDS.items() if key in lower), None)
        storage = re.search(r"(?<!\d)(\d{2,4})\s*(?:gb|g)(?!\w)", lower)
        tb = re.search(r"(?<!\d)(\d+)\s*tb(?!\w)", lower)
        storage_gb = int(storage.group(1)) if storage else int(tb.group(1)) * 1024 if tb else None
        model_match = re.search(
            r"(iphone\s*\d{1,2}(?:\s*(?:pro|max|plus|mini)){0,2}|s\d{2}\s*ultra)", lower
        )
        model = model_match.group(1).title().replace("Iphone", "iPhone") if model_match else None
        region = location or next((value for key, value in REGIONS.items() if key in text), None)
        normalized_condition = next(
            (value for key, value in CONDITIONS.items() if key in (condition or text)), None
        )
        return NormalizedListing(brand, model, storage_gb, region, normalized_condition)
