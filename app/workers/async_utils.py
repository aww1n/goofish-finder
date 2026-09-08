import asyncio
from collections.abc import Coroutine
from typing import Any

from app.db.session import engine


async def _run_and_dispose[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    try:
        return await coroutine
    finally:
        # Celery opens a fresh event loop for every synchronous task wrapper.
        # Do not retain asyncpg connections that belong to a loop being closed.
        await engine.dispose()


def run_async[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(_run_and_dispose(coroutine))
