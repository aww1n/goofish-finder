from aiogram import Dispatcher

from app.bot.handlers import router
from app.bot.middlewares.database import DatabaseMiddleware


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseMiddleware())
    dispatcher.include_router(router)
    return dispatcher
