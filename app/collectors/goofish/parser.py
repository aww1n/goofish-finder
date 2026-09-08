from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field


class InspectionService(BaseModel):
    available: bool = False
    type: str | None = None
    version: str | None = None
    mandatory: bool = False
    description: str | None = None
    promise_items: list[str] = Field(default_factory=list)
    service_url: str | None = None
    category: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    detected_by: Literal["structured", "dom", "metadata", "ocr"] | None = None

    @property
    def inspection_service_detected(self) -> bool:
        return self.available


SUPPORTED_MARKERS = (
    "验货宝",
    "本宝贝只走验货宝",
    "支持验货宝",
    "必须通过验货宝",
    "下单后先验货再确认购买",
)
MANDATORY_MARKERS = ("只走验货宝", "必须通过验货宝", "必须走验货宝")


def _contains_marker(values: Iterable[str]) -> bool:
    return any(marker in value for value in values for marker in SUPPORTED_MARKERS)


def _is_mandatory(values: Iterable[str]) -> bool:
    return any(marker in value for value in values for marker in MANDATORY_MARKERS)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for nested in value.values() for text in _strings(nested)]
    if isinstance(value, list | tuple):
        return [text for nested in value for text in _strings(nested)]
    return []


def parse_appraise_info(appraise_info: Mapping[str, Any] | None) -> InspectionService:
    if not appraise_info:
        return InspectionService()
    raw = dict(appraise_info)
    values = _strings(raw)
    title = raw.get("serviceDetailTitle")
    available = bool(
        title == "验货宝"
        or raw.get("yhbVersion")
        or raw.get("serviceUrl")
        or _contains_marker(values)
    )
    promise_items = raw.get("servicePromiseItems")
    if not isinstance(promise_items, list):
        promise_items = []
    return InspectionService(
        available=available,
        type="验货宝" if available else None,
        version=str(raw["yhbVersion"]) if raw.get("yhbVersion") is not None else None,
        mandatory=available and _is_mandatory(values),
        description=raw.get("serviceDescription") or raw.get("additionalDescription"),
        promise_items=[str(item) for item in promise_items],
        service_url=raw.get("serviceUrl"),
        category=str(raw["category"]) if raw.get("category") is not None else None,
        raw=raw,
        detected_by="structured" if available else None,
    )


def detect_inspection_service(
    *,
    appraise_info: Mapping[str, Any] | None = None,
    dom_service_text: Iterable[str] = (),
    accessibility_labels: Iterable[str] = (),
    element_attributes: Iterable[str] = (),
    page_metadata: Mapping[str, Any] | None = None,
    ocr_text: Iterable[str] = (),
) -> InspectionService:
    """Detect service evidence by priority; product description is deliberately excluded."""
    structured = parse_appraise_info(appraise_info)
    if structured.available:
        return structured
    sources = (
        ("dom", [*dom_service_text, *accessibility_labels, *element_attributes]),
        ("metadata", _strings(page_metadata or {})),
        ("ocr", list(ocr_text)),
    )
    for source, values in sources:
        if _contains_marker(values):
            return InspectionService(
                available=True,
                type="验货宝",
                mandatory=_is_mandatory(values),
                detected_by=source,
            )
    return InspectionService()
