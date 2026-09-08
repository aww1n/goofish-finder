from decimal import Decimal

from app.collectors.base import RawListing
from app.core.constants import InspectionFilter
from app.db.models import SearchTask


def passes_hard_filters(item: RawListing, task: SearchTask, normalized: dict[str, object]) -> bool:
    if task.min_price is not None and item.price < task.min_price:
        return False
    if task.max_price is not None and item.price > task.max_price:
        return False
    if task.storage_options and str(normalized.get("storage_gb")) not in task.storage_options:
        return False
    if task.conditions and normalized.get("condition") not in task.conditions:
        return False
    if task.locations and "any" not in task.locations and item.location not in task.locations:
        return False
    if task.seller_min_rating is not None and (
        not item.seller or item.seller.rating is None or item.seller.rating < task.seller_min_rating
    ):
        return False
    inspection_filter = getattr(task, "inspection_filter", InspectionFilter.ANY)
    available = normalized.get("inspection_service_available") is True
    mandatory = normalized.get("inspection_service_mandatory") is True
    if inspection_filter == InspectionFilter.WITH_INSPECTION and not available:
        return False
    if inspection_filter == InspectionFilter.MANDATORY_INSPECTION and not (available and mandatory):
        return False
    if inspection_filter == InspectionFilter.WITHOUT_INSPECTION and available:
        return False
    return not (
        task.seller_min_sales is not None
        and (
            not item.seller
            or item.seller.sales_count is None
            or item.seller.sales_count < task.seller_min_sales
        )
    )


def percent_below(price: Decimal, median: Decimal) -> Decimal:
    return ((median - price) / median * 100).quantize(Decimal("0.1")) if median else Decimal(0)
