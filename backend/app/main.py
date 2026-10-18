import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai import providers
from app.api import (actions, advisor, agent, auth, billing, collections, customers, finance, ledger, payables,
                     products, referrals, reports, settings, team, transactions)
from app.config import get_settings
from app.db import init_db
from app.jobs import scheduler

logging.basicConfig(level=logging.INFO)

s = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = scheduler.start()
    yield
    if task:
        task.cancel()


app = FastAPI(title=s.app_name, version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=s.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Lender-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if s.cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if not request.url.path.startswith(("/docs", "/openapi.json", "/redoc")):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "llm_providers": [p.name for p in providers.build_providers()] or ["templates"]}


for r in (auth, transactions, ledger, collections, customers, products, actions, advisor, payables, finance,
          reports, agent, settings, team, billing, referrals):
    app.include_router(r.router)
