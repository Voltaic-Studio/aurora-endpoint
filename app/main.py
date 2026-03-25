from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import router
from app.clients.llm import OpenRouterClient
from app.clients.messages_api import MessagesApiClient
from app.config import Settings
from app.services.cache_service import MessageCacheService
from app.services.qa_service import QAService
from app.services.retrieval_service import RetrievalService
from app.utils.settings_defaults import HTTP_TIMEOUT_SECONDS

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=5.0)
    http_client = httpx.AsyncClient(timeout=timeout)

    messages_client = MessagesApiClient(http_client=http_client, settings=settings)
    cache_service = MessageCacheService(settings=settings, messages_client=messages_client)
    retrieval_service = RetrievalService(settings=settings)
    llm_client = OpenRouterClient(http_client=http_client, settings=settings)
    qa_service = QAService(
        cache_service=cache_service,
        retrieval_service=retrieval_service,
        llm_client=llm_client,
    )

    app.state.settings = settings
    app.state.cache_service = cache_service
    app.state.qa_service = qa_service

    await cache_service.start()

    try:
        yield
    finally:
        await cache_service.stop()
        await http_client.aclose()


app = FastAPI(title="Aurora Messages QA Service", lifespan=lifespan)
app.include_router(router)
