from __future__ import annotations

import math
import re
import unicodedata

from app.schemas import IndexedMessage, MessageRecord
from app.utils.settings_defaults import RETRIEVAL_TOP_K, SEMANTIC_MIN_SIMILARITY

NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


class RetrievalService:
    @property
    def top_k(self) -> int:
        return RETRIEVAL_TOP_K

    def resolve_member_scope(
        self,
        question: str,
        messages_by_user_id: dict[str, list[IndexedMessage]],
        user_names_by_id: dict[str, str],
    ) -> tuple[str | None, list[IndexedMessage]]:
        normalized_question = self._normalize_text(question)
        if not normalized_question:
            return None, []

        alias_matches: list[tuple[int, str]] = []
        for alias, user_id in self._build_alias_lookup(user_names_by_id).items():
            if self._contains_alias(normalized_question, alias):
                alias_matches.append((len(alias), user_id))

        if not alias_matches:
            return None, [message for messages in messages_by_user_id.values() for message in messages]

        matched_user_ids = {user_id for _, user_id in alias_matches}
        if len(matched_user_ids) != 1:
            return None, [message for messages in messages_by_user_id.values() for message in messages]

        user_id = max(alias_matches, key=lambda item: item[0])[1]
        return user_id, messages_by_user_id.get(user_id, [])

    def retrieve_semantic(
        self,
        query_embedding: list[float],
        candidates: list[IndexedMessage],
    ) -> list[IndexedMessage]:
        query_norm = math.sqrt(sum(value * value for value in query_embedding))
        if query_norm == 0.0:
            return []

        scored_messages: list[tuple[float, IndexedMessage]] = []
        for candidate in candidates:
            similarity = self._cosine_similarity(
                left_embedding=query_embedding,
                left_norm=query_norm,
                right_embedding=candidate.embedding,
                right_norm=candidate.embedding_norm,
            )
            if similarity >= SEMANTIC_MIN_SIMILARITY:
                scored_messages.append((similarity, candidate))

        scored_messages.sort(key=lambda item: (-item[0], item[1].record.timestamp), reverse=False)
        return [candidate for _, candidate in scored_messages[: self.top_k]]

    @staticmethod
    def build_context(messages: list[IndexedMessage]) -> str:
        lines = []
        for message in messages:
            record = message.record
            lines.append(
                f"[{record.id}] {record.user_name} | {record.timestamp} | {record.message}"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_alias_lookup(user_names_by_id: dict[str, str]) -> dict[str, str]:
        alias_counts: dict[str, set[str]] = {}

        for user_id, user_name in user_names_by_id.items():
            normalized_name = RetrievalService._normalize_text(user_name)
            if not normalized_name:
                continue

            aliases = {normalized_name}
            name_parts = normalized_name.split()
            if name_parts:
                aliases.add(name_parts[0])
                aliases.add(name_parts[-1])

            for alias in aliases:
                alias_counts.setdefault(alias, set()).add(user_id)

        return {
            alias: next(iter(user_ids))
            for alias, user_ids in alias_counts.items()
            if len(user_ids) == 1
        }

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        collapsed = NORMALIZE_RE.sub(" ", ascii_value.lower()).strip()
        return collapsed

    @staticmethod
    def _contains_alias(question: str, alias: str) -> bool:
        return f" {alias} " in f" {question} "

    @staticmethod
    def _cosine_similarity(
        left_embedding: list[float],
        left_norm: float,
        right_embedding: list[float],
        right_norm: float,
    ) -> float:
        denominator = left_norm * right_norm
        if denominator == 0.0:
            return 0.0

        dot_product = sum(left * right for left, right in zip(left_embedding, right_embedding, strict=True))
        return dot_product / denominator
