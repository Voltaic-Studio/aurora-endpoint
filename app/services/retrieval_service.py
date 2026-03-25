from __future__ import annotations

from collections import Counter

from app.config import Settings
from app.schemas import MessageRecord
from app.utils.constants import BROAD_QUERY_TERMS, RETRIEVAL_STOPWORDS, TOKEN_RE
from app.utils.settings_defaults import RETRIEVAL_BROAD_QUERY_TOP_K, RETRIEVAL_TOP_K


class RetrievalService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def top_k(self) -> int:
        return RETRIEVAL_TOP_K

    def top_k_for_question(self, question: str) -> int:
        question_tokens = set(self._tokenize(question))
        if question_tokens & BROAD_QUERY_TERMS:
            return RETRIEVAL_BROAD_QUERY_TOP_K
        return self.top_k

    def retrieve(self, question: str, messages: list[MessageRecord]) -> list[MessageRecord]:
        scored_messages = self.retrieve_scored(question, messages)
        top_messages = [message for _, message in scored_messages[: self.top_k_for_question(question)]]

        if top_messages:
            return top_messages

        return messages[: self.top_k_for_question(question)]

    def retrieve_scored(self, question: str, messages: list[MessageRecord]) -> list[tuple[float, MessageRecord]]:
        question_tokens = self._tokenize(question)
        if not question_tokens:
            return []

        candidate_messages = self._filter_messages_by_user_name(question, messages)
        scored_messages: list[tuple[float, MessageRecord]] = []
        question_counts = Counter(question_tokens)
        question_text = question.lower()

        for message in candidate_messages:
            haystack = f"{message.user_name} {message.message}".lower()
            message_tokens = self._tokenize(haystack)
            if not message_tokens:
                continue

            message_counts = Counter(message_tokens)
            overlap = sum(min(question_counts[token], message_counts[token]) for token in question_counts)
            unique_overlap = len(set(question_tokens) & set(message_tokens))
            phrase_bonus = 1.5 if message.user_name.lower() in question_text else 0.0
            contains_question_fragment = 1.0 if any(token in haystack for token in question_tokens[:3]) else 0.0

            score = (overlap * 2.0) + unique_overlap + phrase_bonus + contains_question_fragment
            if score > 0:
                scored_messages.append((score, message))

        scored_messages.sort(key=lambda item: (-item[0], item[1].timestamp), reverse=False)
        return scored_messages

    @staticmethod
    def _filter_messages_by_user_name(
        question: str, messages: list[MessageRecord]
    ) -> list[MessageRecord]:
        question_text = question.lower()
        matched_names = {
            message.user_name
            for message in messages
            if message.user_name and message.user_name.lower() in question_text
        }

        if len(matched_names) != 1:
            return messages

        matched_name = next(iter(matched_names))
        return [message for message in messages if message.user_name == matched_name]

    @staticmethod
    def build_context(messages: list[MessageRecord]) -> str:
        lines = []
        for message in messages:
            lines.append(
                f"[{message.id}] {message.user_name} | {message.timestamp} | {message.message}"
            )
        return "\n".join(lines)

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        return [
            token for token in TOKEN_RE.findall(value.lower()) if token not in RETRIEVAL_STOPWORDS
        ]
