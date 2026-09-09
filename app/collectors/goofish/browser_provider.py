import asyncio
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from app.collectors.base import (
    GoofishProvider,
    ProviderAccessChallenge,
    ProviderAuthRequired,
    ProviderError,
    RawListing,
    RawSeller,
)
from app.core.config import Settings

PRICE_PATTERN = re.compile(r"¥\s*([\d,]+(?:\.\d+)?)")
RATING_PATTERN = re.compile(r"好评率\s*(\d+(?:\.\d+)?)%")
SALES_PATTERN = re.compile(r"卖出\s*(\d+)\s*件")
CHALLENGE_MARKERS = ("安全验证", "验证码", "滑动验证", "请完成验证", "访问异常")
LOGIN_MARKERS = ("立即登录", "扫码登录", "短信登录")
CONDITION_MARKERS = ("全新未拆封", "全新", "几乎全新", "轻微使用痕迹", "明显使用痕迹")


def external_id_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("id")
    return values[0] if values and values[0].isdigit() else None


def price_from_text(text: str) -> Decimal | None:
    match = PRICE_PATTERN.search(text)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None


def title_from_text(text: str) -> str | None:
    ignored = {
        "卖家信用极好",
        "卖家信用优秀",
        "包邮",
        "全新",
        "几乎全新",
        "轻微使用痕迹",
    }
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = [
        line
        for line in lines
        if line not in ignored
        and not line.startswith("¥")
        and not re.fullmatch(r"[\d,.]+", line)
        and "人想要" not in line
    ]
    return candidates[0][:500] if candidates else None


class BrowserGoofishProvider(GoofishProvider):
    """Goofish public-web collector using a user-owned persistent browser session."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._item_urls: dict[str, str] = {}

    async def _context_instance(self) -> BrowserContext:
        if self._context:
            return self._context
        self._playwright = await async_playwright().start()
        profile = Path(self.settings.goofish_browser_profile)
        profile.mkdir(parents=True, exist_ok=True)
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile.resolve()),
            channel=self.settings.goofish_browser_channel,
            headless=self.settings.goofish_browser_headless,
            chromium_sandbox=True,
            locale="zh-CN",
            viewport={"width": 1440, "height": 1000},
        )
        return self._context

    async def _throttle(self) -> None:
        delay = self.settings.goofish_min_interval_seconds - (
            time.monotonic() - self._last_request_at
        )
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_request_at = time.monotonic()

    async def _open(self, url: str) -> tuple[Page, str, list[dict[str, Any]]]:
        async with self._lock:
            await self._throttle()
            context = await self._context_instance()
            page = await context.new_page()
            captured_json: list[dict[str, Any]] = []

            async def capture(response: Any) -> None:
                if "json" not in response.headers.get("content-type", ""):
                    return
                try:
                    value = await response.json()
                except (PlaywrightError, ValueError):
                    return
                if isinstance(value, dict):
                    captured_json.append(value)

            page.on("response", capture)
            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.goofish_timeout_seconds * 1000,
                )
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=self.settings.goofish_timeout_seconds * 1000
                    )
                except PlaywrightTimeoutError:
                    pass
                body = await page.locator("body").inner_text()
                self._validate_access(body)
                return page, body, captured_json
            except (ProviderAuthRequired, ProviderAccessChallenge):
                await page.close()
                raise
            except Exception as exc:
                await page.close()
                raise ProviderError(
                    f"Goofish browser request failed: {type(exc).__name__}"
                ) from exc

    @staticmethod
    def _validate_access(body: str) -> None:
        if any(marker in body for marker in CHALLENGE_MARKERS):
            raise ProviderAccessChallenge(
                "Goofish показал проверку доступа; автоматический сбор остановлен"
            )

    async def search(self, task: Any, *, page: int = 1) -> list[RawListing]:
        # The public UI currently exposes scrolling rather than a documented page parameter.
        if page != 1:
            return []
        url = f"https://www.goofish.com/search?q={quote_plus(task.query)}"
        browser_page, body, _responses = await self._open(url)
        try:
            cards = await browser_page.locator('a[href*="/item"]').evaluate_all(
                """links => links.map(link => ({
                    href: link.href,
                    text: link.innerText || '',
                    images: Array.from(link.querySelectorAll('img'))
                      .map(img => img.currentSrc || img.src).filter(Boolean)
                }))"""
            )
            if not cards:
                if any(marker in body for marker in LOGIN_MARKERS) or "加载中" in body:
                    raise ProviderAuthRequired(
                        "Для поиска Goofish требуется вход. Выполните: "
                        ".venv/bin/python -m app.collectors.goofish.login"
                    )
                raise ProviderError("Goofish search returned no readable item cards")
            listings: list[RawListing] = []
            seen: set[str] = set()
            for card in cards:
                item_id = external_id_from_url(card["href"])
                price = price_from_text(card["text"])
                title = title_from_text(card["text"])
                if not item_id or item_id in seen or price is None or not title:
                    continue
                seen.add(item_id)
                self._item_urls[item_id] = card["href"]
                listings.append(
                    RawListing(
                        external_id=item_id,
                        title=title,
                        price=price,
                        currency="CNY",
                        url=card["href"],
                        images=list(dict.fromkeys(card.get("images", []))),
                        condition=next(
                            (value for value in CONDITION_MARKERS if value in card["text"]), None
                        ),
                        raw={"search_card_text": card["text"], "source": "browser"},
                    )
                )
            return listings
        finally:
            await browser_page.close()

    async def get_item_details(self, item_id: str) -> RawListing:
        url = self._item_urls.get(item_id, f"https://www.goofish.com/item?id={item_id}")
        page, body, responses = await self._open(url)
        try:
            title = (await page.title()).removesuffix("_闲鱼").strip()
            price = price_from_text(body)
            if not title or price is None:
                raise ProviderError("Goofish item page does not contain a title or price")
            images = await page.locator("img").evaluate_all(
                """images => images.map(img => ({
                    src: img.currentSrc || img.src,
                    width: img.naturalWidth,
                    height: img.naturalHeight
                })).filter(x => x.src && x.width >= 300 && x.height >= 300).map(x => x.src)"""
            )
            appraise_info = self._find_mapping(responses, "appraiseInfo")
            rating = RATING_PATTERN.search(body)
            sales = SALES_PATTERN.search(body)
            seller_name, location = self._seller_and_location(body)
            return RawListing(
                external_id=item_id,
                title=title[:500],
                price=price,
                currency="CNY",
                url=url,
                images=list(dict.fromkeys(images)),
                description=self._description(body, title),
                seller=RawSeller(
                    external_id=f"browser:{seller_name or item_id}",
                    name=seller_name,
                    rating=Decimal(rating.group(1)) if rating else None,
                    sales_count=int(sales.group(1)) if sales else None,
                ),
                location=location,
                condition=next((value for value in CONDITION_MARKERS if value in body), None),
                raw={"page_text": body[:20000], "source": "browser", "details_complete": True},
                appraise_info=appraise_info,
                inspection_evidence={"dom_service_text": self._inspection_dom_lines(body)},
            )
        finally:
            await page.close()

    @classmethod
    def _find_mapping(cls, values: Any, key: str) -> dict[str, Any] | None:
        if isinstance(values, dict):
            found = values.get(key)
            if isinstance(found, dict):
                return found
            for nested in values.values():
                result = cls._find_mapping(nested, key)
                if result:
                    return result
        elif isinstance(values, list):
            for nested in values:
                result = cls._find_mapping(nested, key)
                if result:
                    return result
        return None

    @staticmethod
    def _seller_and_location(body: str) -> tuple[str | None, str | None]:
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        rating_index = next((i for i, line in enumerate(lines) if "好评率" in line), None)
        if rating_index is None:
            return None, None
        seller = lines[rating_index - 4] if rating_index >= 4 else None
        location = lines[rating_index - 3] if rating_index >= 3 else None
        return seller, location

    @staticmethod
    def _description(body: str, title: str) -> str | None:
        start = body.find(title)
        if start < 0:
            return None
        section = body[start + len(title) :]
        end = section.find("聊一聊")
        return section[:end].strip()[:5000] if end >= 0 else section.strip()[:5000]

    @staticmethod
    def _inspection_dom_lines(body: str) -> list[str]:
        return [line.strip() for line in body.splitlines() if "验货宝" in line][:20]

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
