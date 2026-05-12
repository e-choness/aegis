from __future__ import annotations
import asyncio
import logging
import os
import yaml
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api.v1.health import router as health_router
from .api.v1.inference import router as inference_router
from .api.v1.admin import router as admin_router
from .api.v1.rag import router as rag_router
from .services.audit import AuditLogger
from .services.auth_manager import AuthConfig, AuthManager
from .services.budget import BudgetService
from .services.health import ProviderHealth
from .services.inference import InferenceService
from .services.model_cache import ModelCache
from .services.model_lifecycle import ModelLifecycleManager
from .services.pii import PIIMasker
from .services.tier2_failover import EndpointConfig, Tier2Failover
from .providers.external_llm_provider import ExternalLLMProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

logger = logging.getLogger("aegis.main")

CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "providers.yaml"


def _load_providers_config() -> dict:
    """Load providers.yaml configuration."""
    if not CONFIG_PATH.exists():
        logger.warning("config/providers.yaml not found, skipping Tier 2 initialization")
        return {}
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    health = ProviderHealth()
    budget = BudgetService()
    audit = AuditLogger()
    pii = PIIMasker()  # loads spacy model at startup

    # Load configuration
    config = _load_providers_config()
    tier2_config = config.get("tier_2", {})
    model_aliases = config.get("model_aliases", {})

    # Initialize Tier 2 services if enabled
    external_llm_provider = None
    model_lifecycle = None
    if tier2_config and os.environ.get("TIER_2_ENABLED", "false").lower() == "true":
        try:
            # 1. Initialize model cache (TTL-based, no network)
            model_cache = ModelCache(ttl_seconds=tier2_config.get("model_discovery", {}).get("cache_ttl_seconds", 300))
            logger.info("ModelCache initialized (TTL=%ds)", model_cache._ttl_seconds)

            # 2. Initialize failover (load balancing + circuit breaker)
            endpoint_configs = [
                EndpointConfig(url=ep["url"], weight=ep.get("weight", 1))
                for ep in tier2_config.get("endpoints", [])
            ]
            failover = Tier2Failover(
                endpoints=endpoint_configs,
                timeout_seconds=tier2_config.get("failover", {}).get("timeout_seconds", 5.0),
                circuit_breaker_failures=tier2_config.get("failover", {}).get("circuit_breaker_failures", 3),
                circuit_breaker_recovery_seconds=tier2_config.get("failover", {}).get("circuit_breaker_recovery_seconds", 60),
            )
            logger.info("Tier2Failover initialized with %d endpoints", len(endpoint_configs))

            # 3. Initialize authentication (Bearer token or mTLS)
            auth_config_dict = tier2_config.get("auth", {})
            auth_type = os.environ.get(auth_config_dict.get("type_env", "TIER_2_AUTH_TYPE"), "api_key")
            auth_config = AuthConfig(auth_type=auth_type)

            if auth_type == "api_key":
                auth_config.token = os.environ.get(
                    auth_config_dict.get("api_key", {}).get("token_env", "TIER_2_API_KEY")
                )
                auth_config.header_format = auth_config_dict.get("api_key", {}).get("header_format", "Authorization: Bearer {token}")
            elif auth_type == "mtls":
                auth_config.cert_path = os.environ.get(auth_config_dict.get("mtls", {}).get("cert_path_env", "TIER_2_CERT_PATH"))
                auth_config.key_path = os.environ.get(auth_config_dict.get("mtls", {}).get("key_path_env", "TIER_2_KEY_PATH"))
                auth_config.ca_path = os.environ.get(auth_config_dict.get("mtls", {}).get("ca_path_env", "TIER_2_CA_PATH"))
                auth_config.verify_hostname = auth_config_dict.get("mtls", {}).get("verify_hostname", True)

            auth_manager = AuthManager(auth_config)
            logger.info("AuthManager initialized (auth_type=%s)", auth_type)

            # 4. Initialize ExternalLLMProvider
            external_llm_provider = ExternalLLMProvider(
                endpoints=endpoint_configs,
                auth_manager=auth_manager,
                cache=model_cache,
                failover=failover,
                timeout_seconds=tier2_config.get("failover", {}).get("timeout_seconds", 5.0),
            )
            logger.info("ExternalLLMProvider initialized")

            # 5. Initialize ModelLifecycleManager (no network blocking)
            model_lifecycle = ModelLifecycleManager(external_llm_provider, model_cache)
            # Declare models from config (instant, no network)
            for alias, model_id in model_aliases.items():
                model_lifecycle.declare_models(alias, [model_id])
            logger.info("ModelLifecycleManager initialized with %d aliases", len(model_aliases))

            # 6. Non-blocking warmup (health checks, no model pulls)
            app.state.external_llm_provider = external_llm_provider
            app.state.model_lifecycle = model_lifecycle
            app.state.model_cache = model_cache
            app.state.tier2_failover = failover

            # Schedule warmup as background task (10s timeout, won't block startup)
            async def warmup_task():
                try:
                    await asyncio.wait_for(model_lifecycle.warmup(), timeout=10.0)
                    logger.info("Model lifecycle warmup completed")
                except asyncio.TimeoutError:
                    logger.warning("Model lifecycle warmup timed out (gateway continues)")
                except Exception as e:
                    logger.warning("Model lifecycle warmup failed: %s (gateway continues)", e)

            asyncio.create_task(warmup_task())

        except Exception as e:
            logger.error("Tier 2 initialization failed: %s (continuing without Tier 2)", e)
    else:
        logger.info("TIER_2_ENABLED not set or false — Tier 2 disabled")

    # Initialize InferenceService
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

    logger.info("Aegis AI Gateway started (Phase 1)")
    yield
    logger.info("Aegis AI Gateway shutting down")


app = FastAPI(
    title="Aegis AI Gateway",
    version="0.3.0",
    description="Enterprise AI governance gateway — Phase 1",
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
app.include_router(admin_router)
app.include_router(rag_router)


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
