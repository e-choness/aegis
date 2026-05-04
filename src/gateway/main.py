from __future__ import annotations
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api.v1.health import router as health_router
from .api.v1.inference import router as inference_router
from .api.v1.rag import router as rag_router
from .services.audit import AuditLogger
from .services.budget import BudgetService
from .services.health import ProviderHealth
from .services.inference import InferenceService
from .services.pii import PIIMasker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger("aegis.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    health = ProviderHealth()
    budget = BudgetService()
    audit = AuditLogger()
    pii = PIIMasker()  # loads spacy model at startup
    app.state.inference_service = InferenceService(
        health=health, budget=budget, audit=audit, pii_masker=pii
    )

    vectordb_url = os.environ.get("VECTORDB_URL")
    if vectordb_url:
        import asyncpg
        from .services.rag import RAGService
        pool = await asyncpg.create_pool(vectordb_url, min_size=2, max_size=10)
        app.state.rag_service = RAGService(db_pool=pool, health_checker=health)
        logger.info("RAG service initialized (vectordb connected)")
    else:
        logger.info("VECTORDB_URL not set — RAG service disabled")

    logger.info("Aegis AI Gateway started (Phase 3)")
    yield
    logger.info("Aegis AI Gateway shutting down")


app = FastAPI(
    title="Aegis AI Gateway",
    version="0.3.0",
    description="Enterprise AI governance gateway — Phase 3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(inference_router)
app.include_router(health_router)
app.include_router(rag_router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
