from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session

app = FastAPI(title="GOFISH FINDER internal API", docs_url=None, redoc_url=None)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready(db: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


def require_admin(authorization: str | None = Header(None)) -> None:
    expected = get_settings().admin_token
    if not expected or authorization != f"Bearer {expected.get_secret_value()}":
        raise HTTPException(401, "Unauthorized")


@app.get("/admin/status", dependencies=[Depends(require_admin)])
async def admin_status() -> dict[str, str]:
    return {"provider": get_settings().goofish_provider}
