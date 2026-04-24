"""
main.py

Entry point da aplicacao FastAPI do agente SDR WhatsApp.

Startup:
  - Configura logging
  - Cria/verifica tabela chat_sessions no Supabase

Shutdown:
  - (sem acoes necessarias no modo serverless Vercel)

Nota Vercel/serverless:
  - O worker de fila (run_worker) foi removido — sem processo continuo.
  - O scheduler APScheduler foi removido — substituido por Vercel Cron Jobs.
  - Use o endpoint POST /cron/followup (acionado a cada 30min pelo Vercel).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI

from config.settings import settings
from memory.chat import create_table_if_not_exists
from webhook.router import router as webhook_router


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    _configure_logging()
    logger = logging.getLogger(__name__)

    logger.info(
        "Iniciando agente SDR | env=%s | llm=%s (%s)",
        settings.APP_ENV,
        settings.LLM_PROVIDER,
        settings.llm_model_resolved,
    )

    try:
        await create_table_if_not_exists()
    except Exception as exc:
        logger.error("Erro ao verificar tabela chat_sessions: %s", exc)

    logger.info("Agente pronto (modo serverless)")

    yield

    # --- Shutdown ---
    logger.info("Encerrando agente...")


app = FastAPI(
    title="Agente SDR WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/")
async def healthcheck():
    return {"status": "ok", "env": settings.APP_ENV}


@app.post("/cron/followup")
async def cron_followup(background_tasks: BackgroundTasks):
    """
    Endpoint acionado pelo Vercel Cron Job a cada 30 minutos.

    Executa a logica de follow-up em background e retorna imediatamente
    para nao bloquear o cron runner do Vercel.
    """
    from followup.scheduler import run_followup
    background_tasks.add_task(run_followup)
    return {"status": "scheduled"}
