from dataclasses import dataclass
from decimal import Decimal
from statistics import median


@dataclass(frozen=True, slots=True)
class MarketData:
    median: Decimal
    average: Decimal
    minimum: Decimal
    maximum: Decimal
    percentile_25: Decimal
    sample_size: int

    @property
    def reliable(self) -> bool:
        return self.sample_size >= 5


def calculate_market_price(prices: list[Decimal]) -> MarketData | None:
    if not prices:
        return None
    ordered = sorted(prices)
    index = round((len(ordered) - 1) * 0.25)
    return MarketData(
        median=Decimal(median(ordered)),
        average=sum(ordered) / len(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        percentile_25=ordered[index],
        sample_size=len(ordered),
    )
