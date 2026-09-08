import asyncio

from aiogram import Bot

from app.bot import create_dispatcher
from app.core.config import get_settings
from app.core.logging import configure_logging


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError("BOT_TOKEN is required to run the Telegram bot")
    async with Bot(token) as bot:
        await create_dispatcher().start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
