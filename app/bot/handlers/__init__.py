from aiogram import Router

from .main import router as main_router
from .search import router as search_router

router = Router()
router.include_routers(search_router, main_router)
