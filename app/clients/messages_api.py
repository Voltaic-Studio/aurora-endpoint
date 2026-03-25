from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import Settings
from app.schemas import MessageRecord, PaginatedMessages
from app.utils.settings_defaults import (
    MESSAGES_FETCH_RETRIES,
    MESSAGES_PAGE_SIZE,
    MESSAGES_RETRY_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)


class MessagesApiClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._settings = settings

    async def fetch_page(self, skip: int = 0, limit: int | None = None) -> PaginatedMessages:
        page_limit = limit or MESSAGES_PAGE_SIZE
        attempts = MESSAGES_FETCH_RETRIES + 1

        for attempt in range(1, attempts + 1):
            try:
                response = await self._http_client.get(
                    f"{self._settings.messages_api_base_url}/messages/",
                    params={"skip": skip, "limit": page_limit},
                )
                response.raise_for_status()
                return PaginatedMessages.model_validate(response.json())
            except httpx.HTTPStatusError:
                if attempt == attempts:
                    raise
            except httpx.HTTPError:
                if attempt == attempts:
                    raise

            await asyncio.sleep(MESSAGES_RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError("Unreachable retry state while fetching upstream messages")

    async def fetch_all_messages(self) -> list[MessageRecord]:
        all_messages: list[MessageRecord] = []
        seen_ids: set[str] = set()
        skip = 0
        limit = MESSAGES_PAGE_SIZE
        total: int | None = None

        while total is None or skip < total:
            try:
                page = await self.fetch_page(skip=skip, limit=limit)
            except httpx.HTTPStatusError as exc:
                if all_messages and exc.response.status_code in {400, 401, 404}:
                    logger.warning(
                        "Stopping upstream pagination early at skip=%s after %s messages due to status %s",
                        skip,
                        len(all_messages),
                        exc.response.status_code,
                    )
                    break
                raise

            total = page.total
            new_items = [item for item in page.items if item.id not in seen_ids]
            for item in new_items:
                seen_ids.add(item.id)
            all_messages.extend(new_items)

            if not page.items:
                break

            if len(page.items) < limit:
                break

            skip += len(page.items)

        logger.info("Fetched %s messages from upstream API", len(all_messages))
        return all_messages
