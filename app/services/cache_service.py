from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from cachetools import TTLCache

from app.clients.messages_api import MessagesApiClient
from app.config import Settings
from app.schemas import MessageRecord
from app.utils.settings_defaults import CACHE_TTL_SECONDS, REFRESH_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


class MessageCacheService:
    def __init__(self, settings: Settings, messages_client: MessagesApiClient) -> None:
        self._settings = settings
        self._messages_client = messages_client
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

            self._cache["messages"] = {
                "items": messages,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._last_refresh_error = None
            logger.info("Cache refreshed with %s messages", len(messages))

    async def get_messages(self) -> list[MessageRecord]:
        snapshot = self._cache.get("messages")
        if snapshot is None:
            try:
                await self.refresh(force=True)
            except RuntimeError as exc:
                raise RuntimeError("Messages cache is unavailable because upstream fetch failed") from exc
            snapshot = self._cache.get("messages")

        if snapshot is None:
            raise RuntimeError("Messages cache is unavailable")

        return snapshot["items"]

    def get_status(self) -> dict[str, Any]:
        snapshot = self._cache.get("messages")
        if snapshot is None:
            return {
                "ready": False,
                "count": 0,
                "updated_at": None,
                "last_error": self._last_refresh_error,
            }

        items: list[MessageRecord] = snapshot["items"]
        return {
            "ready": True,
            "count": len(items),
            "updated_at": snapshot["updated_at"],
            "last_error": self._last_refresh_error,
        }
