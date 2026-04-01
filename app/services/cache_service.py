from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Any

from cachetools import TTLCache

from app.clients.llm import OpenRouterClient
from app.clients.messages_api import MessagesApiClient
from app.config import Settings
from app.schemas import CachedMessageIndex, IndexedMessage, MessageRecord
from app.utils.settings_defaults import CACHE_TTL_SECONDS, REFRESH_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class MessageCacheService:
    def __init__(
        self,
        settings: Settings,
        messages_client: MessagesApiClient,
        llm_client: OpenRouterClient,
    ) -> None:
        self._settings = settings
        self._messages_client = messages_client
        self._llm_client = llm_client
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1, ttl=CACHE_TTL_SECONDS)
        self._refresh_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None
        self._last_refresh_error: str | None = None

    async def start(self) -> None:
        await self.refresh(force=True)
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        if self._refresh_task is None:
            return

        self._refresh_task.cancel()
        try:
            await self._refresh_task
        except asyncio.CancelledError:
            pass

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            try:
                await self.refresh(force=True)
            except Exception:
                logger.exception("Background cache refresh failed")

    async def refresh(self, force: bool = False) -> None:
        async with self._refresh_lock:
            if not force and "messages" in self._cache:
                return

            try:
                messages = await self._messages_client.fetch_all_messages()
            except Exception as exc:
                self._last_refresh_error = str(exc)
                raise RuntimeError("Unable to refresh messages cache from upstream API") from exc

            if not messages:
                self._last_refresh_error = "Upstream API returned no messages"
                raise RuntimeError("Upstream API returned no messages")

            indexed_messages = await self._build_index(messages)
            messages_by_user_id: dict[str, list[IndexedMessage]] = {}
            user_names_by_id: dict[str, str] = {}

            for indexed_message in indexed_messages:
                record = indexed_message.record
                user_names_by_id[record.user_id] = record.user_name
                messages_by_user_id.setdefault(record.user_id, []).append(indexed_message)

            self._cache["messages"] = {
                "snapshot": CachedMessageIndex(
                    items=messages,
                    indexed_items=indexed_messages,
                    messages_by_user_id=messages_by_user_id,
                    user_names_by_id=user_names_by_id,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            }
            self._last_refresh_error = None
            logger.info("Cache refreshed with %s messages", len(messages))

    async def get_messages(self) -> list[MessageRecord]:
        snapshot = await self.get_snapshot()
        return snapshot.items

    async def get_snapshot(self) -> CachedMessageIndex:
        cache_entry = self._cache.get("messages")
        if cache_entry is None:
            try:
                await self.refresh(force=True)
            except RuntimeError as exc:
                raise RuntimeError("Messages cache is unavailable because upstream fetch failed") from exc
            cache_entry = self._cache.get("messages")

        if cache_entry is None:
            raise RuntimeError("Messages cache is unavailable")

        snapshot = cache_entry.get("snapshot")
        if not isinstance(snapshot, CachedMessageIndex):
            raise RuntimeError("Messages cache snapshot is unavailable")

        return snapshot

    def get_status(self) -> dict[str, Any]:
        cache_entry = self._cache.get("messages")
        if cache_entry is None:
            return {
                "ready": False,
                "count": 0,
                "updated_at": None,
                "last_error": self._last_refresh_error,
            }

        snapshot = cache_entry.get("snapshot")
        if not isinstance(snapshot, CachedMessageIndex):
            return {
                "ready": False,
                "count": 0,
                "updated_at": None,
                "last_error": self._last_refresh_error,
            }

        return {
            "ready": True,
            "count": len(snapshot.items),
            "updated_at": snapshot.updated_at,
            "last_error": self._last_refresh_error,
        }

    async def _build_index(self, messages: list[MessageRecord]) -> list[IndexedMessage]:
        search_texts = [self._build_search_text(message) for message in messages]
        embeddings = await self._llm_client.embed_texts(search_texts)

        indexed_messages: list[IndexedMessage] = []
        for message, embedding in zip(messages, embeddings, strict=True):
            embedding_norm = math.sqrt(sum(value * value for value in embedding))
            if embedding_norm == 0.0:
                continue

            indexed_messages.append(
                IndexedMessage(
                    record=message,
                    embedding=embedding,
                    embedding_norm=embedding_norm,
                )
            )

        return indexed_messages

    @staticmethod
    def _build_search_text(message: MessageRecord) -> str:
        return f"Member: {message.user_name}\nMessage: {message.message}"
