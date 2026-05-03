import logging
import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine
from app.routers import (
    ai_settings,
    bank_accounts,
    bookings,
    chat,
    clarifications,
    clients,
    documents,
    exports,
    skills,
)
from app.routers import dashboard
from app.routers import agent as agent_router
from app.services.supervisor import supervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

os.environ.setdefault("LANGCHAIN_TRACING_V2", str(settings.langchain_tracing_v2).lower())
os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
if settings.langsmith_api_key:
    os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)

app = FastAPI(
    title="AI Buchhaltung",
    description="AI-native bookkeeping service — upload invoices, get DATEV-ready bookings.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Ein interner Fehler ist aufgetreten. Bitte versuchen Sie es erneut.",
            "code": "INTERNAL_ERROR",
        },
    )


app.include_router(bank_accounts.router)
app.include_router(bookings.router)
app.include_router(chat.router)
app.include_router(clarifications.router)
app.include_router(clients.router)
app.include_router(documents.router)
app.include_router(exports.router)
app.include_router(skills.router)
app.include_router(dashboard.router)
app.include_router(agent_router.router)
app.include_router(ai_settings.router)


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Starting autonomous supervisor agent")
    await supervisor.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("Shutting down supervisor and DB connections")
    await supervisor.stop()
    await engine.dispose()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
