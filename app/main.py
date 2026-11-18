from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import SessionLocal
from app.keitaro_payload import normalize_base_url
from app.routers import router
from app.services import seed_settings_from_env


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with SessionLocal() as session:
        seed_settings_from_env(
            session,
            normalize_base_url(settings.keitaro_base_url),
            settings.keitaro_api_key.strip(),
        )
    yield


app = FastAPI(title="Keitaro wrapper", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(router)
