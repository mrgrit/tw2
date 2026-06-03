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
from .routers import (
    admin, auth, cohorts, feedback, infras, battles, leaderboard, monitoring,
    scenarios, users,
)
from .schema_upgrade import ensure_added_columns
from .security import hash_password
from .services.scenario_loader import import_scenarios

log = logging.getLogger("tubewar")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 기존 DB 호환: create_all 이 못 만드는 '기존 테이블의 신규 컬럼' 보강.
        await conn.run_sync(ensure_added_columns)
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
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173",
                   "http://192.168.0.107:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store_headers(request, call_next):
    """API 응답은 절대 캐시 금지 — 사용자별 데이터(인프라/배틀 등)가 브라우저 HTTP 캐시에
    남아 다른 계정에게 노출되는 cross-user 누수를 차단한다.

    fetch() 가 같은 URL(`/infras` 등)을 다른 토큰으로 호출할 때, Cache-Control 이 없으면
    브라우저가 직전 사용자의 200 응답을 재사용할 수 있다 → 반드시 no-store.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Authorization"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "tubewar-api", "version": "0.1.0"}


app.include_router(auth.router)
app.include_router(infras.router)
app.include_router(scenarios.router)
app.include_router(battles.router)
app.include_router(leaderboard.router)
app.include_router(users.router)
app.include_router(cohorts.router)
app.include_router(feedback.router)
app.include_router(monitoring.router)
app.include_router(admin.router)
