"""tubewar FastAPI 진입점.

기동 시:
  1) DB 테이블 자동 생성 (Phase 1; Phase 2 에서 alembic 으로 전환)
  2) admin 계정 부트스트랩 (env ADMIN_*)
"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import User
from .routers import auth, infras, battles, scenarios
from .security import hash_password
from .services.scenario_loader import import_scenarios

log = logging.getLogger("tubewar")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        admin = await s.scalar(select(User).where(User.email == settings.admin_email))
        if not admin:
            admin = User(
                email=settings.admin_email.lower(),
                name=settings.admin_name,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
            s.add(admin)
            await s.commit()
            log.info("bootstrapped admin user: %s", settings.admin_email)
        n = await import_scenarios(s)
        if n:
            log.info("imported %d scenarios from contents/battle-scenarios/", n)
    log.info("tubewar API ready on %s:%s", settings.api_host, settings.api_port)
    yield


app = FastAPI(
    title="tubewar API",
    version="0.1.0",
    description="Cyber battle platform built on 6v6 infrastructure",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "tubewar-api", "version": "0.1.0"}


app.include_router(auth.router)
app.include_router(infras.router)
app.include_router(scenarios.router)
app.include_router(battles.router)
