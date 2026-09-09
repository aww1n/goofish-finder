import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    profile = Path(settings.goofish_browser_profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel=settings.goofish_browser_channel,
            headless=False,
            chromium_sandbox=True,
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.goofish.com/", wait_until="domcontentloaded")
        print("Войдите в Goofish в открытом Chrome. CAPTCHA не обходите.")
        print("После успешного входа вернитесь в терминал и нажмите Enter.")
        await asyncio.to_thread(input)
        await context.close()
        print(f"Сессия сохранена в {profile}")


if __name__ == "__main__":
    asyncio.run(main())
